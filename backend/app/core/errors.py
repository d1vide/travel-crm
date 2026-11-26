from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    VERSION_CONFLICT = "version_conflict"
    INVALID_TRANSITION = "invalid_transition"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    DUPLICATE_CONTACTS = "duplicate_contacts"
    DUPLICATE_REQUIRES_HEAD_REVIEW = "duplicate_requires_head_review"
    PAYMENT_LIMIT_EXCEEDED = "payment_limit_exceeded"
    REFUND_LIMIT_EXCEEDED = "refund_limit_exceeded"
    TOURIST_FORM_CLOSED = "tourist_form_closed"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    NOT_IMPLEMENTED = "not_implemented"


class FieldError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    message: str


class Error(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: ErrorCode
    message: str
    fields: list[FieldError]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, fields=None):
        self.status, self.code, self.message = status, code, message
        self.fields = fields


def error_response(status: int, code: str, message: str, fields=None):
    response = JSONResponse(
        status_code=status,
        content=Error(code=code, message=message, fields=fields or []).model_dump(mode="json"),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
    if status == 401:
        response.headers["WWW-Authenticate"] = "Bearer"
    return response


def register_errors(app: FastAPI):
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, error: ApiError):
        response = error_response(error.status, error.code, error.message, error.fields)
        if error.status == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
            if request.url.path == "/api/auth/refresh":
                response.delete_cookie(
                    "refresh_token",
                    path="/api/auth",
                    httponly=True,
                    secure=request.app.state.settings.cookie_secure,
                    samesite="strict",
                )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, error: RequestValidationError):
        fields = []
        for item in error.errors():
            if item["type"] == "contact_required":
                fields.extend(
                    [
                        FieldError(field="phone", message="Укажите телефон или email"),
                        FieldError(field="email", message="Укажите телефон или email"),
                    ]
                )
                continue
            location = item["loc"]
            if location and location[0] in ("body", "query", "path", "header"):
                location = location[1:]
            path = ".".join(str(part) for part in location) or "body"
            if item["type"] == "json_invalid":
                path = "body"
            message = {
                "missing": "Обязательное поле",
                "extra_forbidden": "Неизвестное поле",
                "string_type": "Ожидается строка",
                "string_too_short": "Поле не должно быть пустым",
                "blank_string": "Поле не должно быть пустым",
                "calendar_date": "Передайте корректную дату YYYY-MM-DD",
                "utc_timestamp": "Передайте корректные дату и время UTC с Z",
                "date_order": "Дата окончания не может быть раньше начала",
                "birth_not_future": "Дата рождения не может быть в будущем",
                "passport_expiry": "Укажите срок действия загранпаспорта",
                "json_invalid": "Передайте корректный JSON",
                "uuid_parsing": "Передайте корректный UUID",
                "uuid_type": "Передайте корректный UUID",
                "literal_error": "Выберите допустимое значение",
                "enum": "Выберите допустимое значение",
                "list_type": "Ожидается список",
                "too_short": "Добавьте хотя бы один элемент",
                "int_type": "Ожидается целое число",
                "int_parsing": "Ожидается целое число",
            }.get(item["type"], "Некорректное значение")
            specific = item["type"] not in ("missing", "extra_forbidden")
            if path == "email" and specific:
                message = "Введите корректный email"
            if path == "phone" and specific:
                message = "Введите корректный телефон"
            if path in {"budget", "max_price"} and specific:
                message = "Передайте неотрицательную сумму строкой с двумя знаками после точки"
            if path == "amount" and specific:
                message = "Передайте положительную сумму строкой с двумя знаками после точки"
            if path in {"version", "request_version"} and specific:
                message = "Укажите целую версию не меньше 1"
            if path == "tourist_count" and specific:
                message = "Введите целое число туристов от 1 до 2147483647"
            fields.append(FieldError(field=path, message=message))
        return error_response(422, "validation_error", "Проверьте данные", fields)

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, error: HTTPException):
        code, message = {
            400: ("validation_error", "Передайте корректный запрос"),
            401: ("unauthorized", "Требуется вход в систему"),
            403: ("forbidden", "Недостаточно прав для этого действия"),
            404: ("not_found", "Запрошенные данные не найдены"),
            405: ("not_found", "Метод недоступен"),
            409: ("conflict", "Запрос конфликтует с текущим состоянием"),
            422: ("validation_error", "Проверьте данные"),
            429: ("rate_limited", "Слишком много запросов. Повторите позже"),
            501: ("not_implemented", "Операция пока недоступна"),
        }.get(
            error.status_code,
            ("server_error", "Ошибка сервера")
            if error.status_code >= 500
            else ("validation_error", "Запрос недоступен"),
        )
        response = error_response(error.status_code, code, message)
        for name, value in (error.headers or {}).items():
            if name.lower() in {"allow", "retry-after"}:
                response.headers[name] = value
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(_request: Request, _error: SQLAlchemyError):
        return error_response(
            503, "server_error", "База данных недоступна или миграции не выполнены"
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _error: Exception):
        return error_response(500, "server_error", "Внутренняя ошибка сервера")
