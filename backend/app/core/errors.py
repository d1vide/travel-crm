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
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def error_response(status: int, code: str, message: str, fields=None):
    return JSONResponse(
        status_code=status,
        content=Error(code=code, message=message, fields=fields or []).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


def register_errors(app: FastAPI):
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, error: ApiError):
        response = error_response(error.status, error.code, error.message)
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
            path = (
                ".".join(
                    str(part)
                    for part in item["loc"]
                    if part not in ("body", "query", "path", "header")
                )
                or "body"
            )
            message = {
                "missing": "Обязательное поле",
                "extra_forbidden": "Неизвестное поле",
                "string_type": "Ожидается строка",
                "string_too_short": "Поле не должно быть пустым",
                "blank_string": "Поле не должно быть пустым",
                "calendar_date": "Передайте корректную дату YYYY-MM-DD",
                "date_order": "Дата окончания не может быть раньше начала",
            }.get(item["type"], "Некорректное значение")
            if path == "email" and item["type"] != "missing":
                message = "Введите корректный email"
            if path == "phone" and item["type"] != "missing":
                message = "Введите корректный телефон"
            if path == "budget" and item["type"] != "missing":
                message = "Передайте неотрицательную сумму строкой с двумя знаками после точки"
            if path == "tourist_count" and item["type"] != "missing":
                message = "Введите целое число туристов от 1 до 2147483647"
            fields.append(FieldError(field=path, message=message))
        return error_response(422, "validation_error", "Проверьте данные", fields)

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, error: HTTPException):
        return error_response(
            error.status_code,
            "not_found" if error.status_code in (404, 405) else "forbidden",
            "Ресурс или метод недоступен",
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(_request: Request, _error: SQLAlchemyError):
        return error_response(
            503, "server_error", "База данных недоступна или миграции не выполнены"
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _error: Exception):
        return error_response(500, "server_error", "Внутренняя ошибка сервера")
