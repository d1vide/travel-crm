# /// script
# requires-python = ">=3.12"
# ///
"""Build the design contract before the backend provides its OpenAPI export."""

import argparse
import copy
import json
import re
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent
STAFF = ["manager", "head"]
FINANCE = ["head", "accountant"]
ALL_STAFF = ["manager", "head", "accountant"]


def ref(name):
    return {"$ref": f"#/$defs/{name}"}


def query(name, schema, description, required=False):
    return {
        "name": name,
        "in": "query",
        "required": required,
        "description": description,
        "schema": schema,
    }


def build():
    domain = json.loads((DIRECTORY / "domain.schema.json").read_text(encoding="utf-8"))
    example_file = json.loads(
        (DIRECTORY / "domain.examples.json").read_text(encoding="utf-8")
    )
    examples = {
        example["schema"]: example["value"] for example in example_file["examples"]
    }
    document = {
        "openapi": "3.1.1",
        "info": {
            "title": "TravelCRM API",
            "version": domain["x-contract-version"],
            "description": "Контракт зафиксирован по результатам сверки сценариев и каркаса фронтенда 15.11.2026. Описывает целевое поведение; сервер ещё реализуется. Условия команд: docs/state-transitions.md. Права проверяются сервером, включая принадлежность каждой заявки.",
        },
        "servers": [{"url": "/"}],
        "security": [{"BearerAuth": []}],
        "x-contract-status": "baseline-fixed-after-source-review",
        "x-implementation-status": "partial",
        "paths": {},
        "components": {
            "schemas": copy.deepcopy(domain["$defs"]),
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                },
                "RefreshCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "refresh_token",
                },
            },
            "parameters": {
                "IdempotencyKey": {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "description": "UUID команды. При повторе того же запроса сохраняется; при новой операции меняется. Область: пользователь/публичная ссылка + HTTP-метод и путь ресурса. Другой body с тем же ключом: 409. Проверка доступа предшествует проверке ключа, проверка повтора предшествует version.",
                    "schema": {"type": "string", "format": "uuid"},
                },
            },
            "responses": {},
        },
    }
    error_codes = {
        "401": "Необходим вход или обновление access-токена",
        "403": "Роль или фильтр недоступны сотруднику",
        "404": "Ресурс не найден, недоступен или публичная ссылка недействительна",
        "409": "Конфликт версии, перехода, ключа повтора, дублей или финансового остатка",
        "422": "Некорректные поля тела или параметры запроса",
        "429": "Слишком много запросов",
        "500": "Внутренняя ошибка сервера",
        "501": "Эндпоинт ещё не реализован в текущей сборке",
        "503": "База данных или сервис недоступны",
    }
    for status, description in error_codes.items():
        code = {
            "401": "unauthorized",
            "403": "forbidden",
            "404": "not_found",
            "409": "conflict",
            "422": "validation_error",
            "429": "rate_limited",
            "500": "server_error",
            "501": "not_implemented",
            "503": "server_error",
        }[status]
        document["components"]["responses"][f"Error{status}"] = {
            "description": description,
            "content": {
                "application/json": {
                    "schema": ref("Error"),
                    "example": {"code": code, "message": description, "fields": []},
                }
            },
        }
    for name, value in examples.items():
        document["components"]["schemas"][name]["examples"] = [value]

    def operation(
        method,
        path,
        operation_id,
        summary,
        response=None,
        body=None,
        roles=STAFF,
        requirements=(),
        status=200,
        parameters=(),
        paginated=False,
        sort=(),
        idempotent=False,
        security=None,
        description="",
    ):
        parameters = list(parameters)
        for name in re.findall(r"\{([^}]+)\}", path):
            parameters.append(
                {
                    "name": name,
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "pattern": "^[A-Za-z0-9_-]{43}$"}
                    if name == "token"
                    else ref("Id"),
                }
            )
        if paginated:
            parameters.extend(
                [
                    query(
                        "page",
                        {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 2147483647,
                            "default": 1,
                        },
                        "Номер страницы с 1",
                    ),
                    query(
                        "page_size",
                        {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "default": 20,
                        },
                        "Размер страницы",
                    ),
                ]
            )
        if sort:
            parameters.append(
                query(
                    "sort",
                    {"type": "string", "enum": list(sort), "default": sort[0]},
                    "Стабильная сортировка; при равенстве добавляется id в том же направлении",
                )
            )
        if idempotent:
            parameters.append({"$ref": "#/components/parameters/IdempotencyKey"})
        responses = {str(status): {"description": summary}}
        if response:
            example = copy.deepcopy(examples[response])
            if operation_id == "issue_tourist_link":
                example.update(
                    purpose="tourists",
                    url="http://localhost:8080/public/tourist-forms/" + "A" * 43,
                )
            if operation_id in {
                "list_request_bookings",
                "create_booking",
                "get_booking",
                "confirm_booking",
                "reject_booking",
            }:
                bookings = example["items"] if response == "BookingPage" else [example]
                for booking in bookings:
                    booking.update(
                        version=2,
                        paid_amount="0.00",
                        reserved_payment_amount="0.00",
                        refunded_amount="0.00",
                        remaining_amount=booking["total_amount"],
                        available_payment_amount=booking["total_amount"],
                        allowed_actions=[],
                    )
                    if operation_id in {"create_booking", "reject_booking"}:
                        booking.update(
                            status="pending_confirmation"
                            if operation_id == "create_booking"
                            else "rejected",
                            version=1 if operation_id == "create_booking" else 2,
                            supplier_booking_number=None,
                            confirmed_at=None,
                            tourists=[],
                            available_payment_amount="0.00",
                            rejection_reason=None
                            if operation_id == "create_booking"
                            else "Учебный отказ поставщика",
                            allowed_actions=["confirm", "reject"]
                            if operation_id == "create_booking"
                            else [],
                        )
            responses[str(status)]["content"] = {
                "application/json": {
                    "schema": ref(response),
                    "example": example,
                },
            }
        for code in error_codes:
            if code == "409" and method == "get":
                continue
            if (
                "public" in roles
                and code in ("401", "403")
                and not (
                    (operation_id == "login" and code == "401")
                    or (path.startswith("/auth/") and code == "403")
                )
            ):
                continue
            responses[code] = {"$ref": f"#/components/responses/Error{code}"}
        requirements = list(requirements)
        if (
            body or any(parameter.get("in") == "query" for parameter in parameters)
        ) and "FR-09" not in requirements:
            requirements.append("FR-09")
        if "public" not in roles and "FR-01" not in requirements:
            requirements.append("FR-01")
        result = {
            "operationId": operation_id,
            "summary": summary,
            "tags": [path.split("/")[1]],
            "x-roles": list(roles),
            "x-requirements": list(requirements),
            "x-implementation-status": "implemented"
            if operation_id
            in {
                "login",
                "refresh_session",
                "logout",
                "get_current_user",
                "list_clients",
                "check_duplicate_clients",
                "create_client",
                "get_client",
                "update_client",
                "list_assignees",
                "list_requests",
                "create_request",
                "get_request",
                "update_request",
                "assign_request",
                "start_work_request",
                "cancel_request",
                "resume_request",
                "list_request_history",
                "list_tours",
                "get_tour",
                "list_client_communications",
                "create_communication",
                "list_request_communications",
                "return_to_work_request",
                "select_request_tour",
                "list_request_selections",
                "create_selection",
                "get_selection",
                "issue_selection_link",
                "revoke_public_link",
                "get_public_selection",
                "issue_tourist_link",
                "get_public_tourist_form",
                "submit_public_tourists",
                "get_request_tourists",
                "replace_request_tourists",
                "list_request_bookings",
                "create_booking",
                "get_booking",
                "confirm_booking",
                "reject_booking",
            }
            else "planned",
            "responses": responses,
            "description": description
            or "Доступ менеджера ограничен его заявками. Для DTO с allowed_actions список учитывает роль, состояние и условия команды; сервер повторно проверяет их при записи.",
        }
        if parameters:
            result["parameters"] = parameters
        if body:
            result["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {"schema": ref(body), "example": examples[body]}
                },
            }
        if security is not None:
            result["security"] = security
        if "public" in roles:
            result["security"] = []
        if path.startswith("/public/"):
            responses[str(status)]["headers"] = {
                "Cache-Control": {
                    "schema": {"const": "no-store"},
                    "description": "Публичные данные не кэшируются",
                },
                "Referrer-Policy": {
                    "schema": {"const": "no-referrer"},
                    "description": "Токен ссылки не передаётся в Referer",
                },
            }
        if operation_id in ("login", "refresh_session", "logout"):
            responses[str(status)]["headers"] = {
                "Set-Cookie": {
                    "schema": {"type": "string"},
                    "description": "refresh_token; HttpOnly; SameSite=Strict; Path=/api/auth; Secure в HTTPS. Login/refresh ротируют cookie, logout очищает её. Сырой refresh отсутствует в JSON.",
                }
            }
        document["paths"].setdefault(path, {})[method] = result

    operation(
        "post",
        "/auth/login",
        "login",
        "Войти сотрудником",
        "AuthResult",
        "LoginInput",
        roles=["public"],
        requirements=["FR-01"],
        description="Проверить email/пароль, вернуть access и профиль; установить refresh-cookie. Демо-вход по роли не является частью API.",
    )
    operation(
        "post",
        "/auth/refresh",
        "refresh_session",
        "Обновить сессию",
        "AuthResult",
        roles=ALL_STAFF,
        requirements=["FR-01"],
        security=[{"RefreshCookie": []}],
        description="Атомарно ротировать refresh-cookie; заменить access. Просроченный или отозванный refresh: 401. Не требует Bearer access.",
    )
    operation(
        "post",
        "/auth/logout",
        "logout",
        "Завершить сессию",
        roles=["public"],
        requirements=["FR-01"],
        status=204,
        description="Отозвать текущую refresh-cookie и очистить её. Повторный выход или отсутствие cookie: 204. Access живёт до своего срока, около 15 минут.",
    )
    operation(
        "get",
        "/auth/me",
        "get_current_user",
        "Текущий сотрудник",
        "User",
        roles=ALL_STAFF,
        requirements=["FR-01"],
    )
    operation(
        "get",
        "/users",
        "list_assignees",
        "Сотрудники для назначения ответственным",
        "UserPage",
        roles=["head"],
        requirements=["FR-08"],
        paginated=True,
        sort=["full_name"],
        description="Только активные manager/head, без email и технических полей учётной записи. Менеджер создаёт заявку на себя; руководитель выбирает ответственного.",
    )

    operation(
        "get",
        "/clients",
        "list_clients",
        "Найти доступных клиентов",
        "ClientPage",
        requirements=["FR-02"],
        paginated=True,
        sort=["-created_at", "full_name", "client_number"],
        parameters=[
            query(
                "q",
                text_schema := {"type": "string", "minLength": 1},
                "Поиск по части имени, нормализованному телефону или email",
            )
        ],
    )
    operation(
        "get",
        "/clients/duplicates",
        "check_duplicate_clients",
        "Проверить совпадения контактов",
        "DuplicateCheckResult",
        requirements=["FR-02"],
        parameters=[
            query("phone", text_schema, "Телефон; нужен phone либо email"),
            query(
                "email",
                {"type": "string", "format": "email"},
                "Email; нужен phone либо email",
            ),
            query(
                "exclude_client_id",
                ref("Id"),
                "Своя карточка, исключаемая при редактировании",
            ),
        ],
        description="Сервер требует хотя бы один контакт, проверяет доступ к exclude_client_id. Возвращает только доступные совпадения. Недоступные совпадения дают requires_head_review без персональных данных.",
    )
    operation(
        "post",
        "/clients",
        "create_client",
        "Создать клиента",
        "Client",
        "ClientCreate",
        requirements=["FR-02"],
        status=201,
        idempotent=True,
        description="При совпадении и duplicate_acknowledged=false: 409 duplicate_contacts. Повтор после проверки менеджером: новый ключ и duplicate_acknowledged=true. Недоступные совпадения: 409 duplicate_requires_head_review до проверки руководителем.",
    )
    operation(
        "get",
        "/clients/{client_id}",
        "get_client",
        "Карточка клиента",
        "Client",
        requirements=["FR-02"],
    )
    operation(
        "put",
        "/clients/{client_id}",
        "update_client",
        "Изменить клиента",
        "Client",
        "ClientUpdate",
        requirements=["FR-02"],
        idempotent=True,
    )

    request_filters = [
        query("status", ref("RequestStatus"), "Статус заявки"),
        query(
            "manager_id", ref("Id"), "Ответственный; менеджер может указать только себя"
        ),
        query("client_id", ref("Id"), "Заявки доступного клиента"),
    ]
    operation(
        "get",
        "/requests",
        "list_requests",
        "Список заявок",
        "RequestPage",
        requirements=["FR-03", "FR-08"],
        parameters=request_filters,
        paginated=True,
        sort=["-created_at", "created_at", "starts_on"],
    )
    operation(
        "post",
        "/requests",
        "create_request",
        "Создать заявку",
        "Request",
        "RequestCreate",
        requirements=["FR-03"],
        status=201,
        idempotent=True,
        description="manager_id=null означает текущего сотрудника; manager может назначить только себя, head — активного manager/head. Начальный статус new назначает сервер.",
    )
    operation(
        "get",
        "/requests/{request_id}",
        "get_request",
        "Карточка заявки",
        "Request",
        requirements=["FR-03", "FR-08"],
    )
    operation(
        "put",
        "/requests/{request_id}",
        "update_request",
        "Изменить пожелания заявки",
        "Request",
        "RequestUpdate",
        requirements=["FR-03", "FR-09"],
        idempotent=True,
    )
    operation(
        "patch",
        "/requests/{request_id}/assignee",
        "assign_request",
        "Сменить ответственного",
        "Request",
        "AssignRequest",
        roles=["head"],
        requirements=["FR-08"],
        idempotent=True,
    )
    for action, body in [
        ("start-work", "ExpectedVersion"),
        ("return-to-work", "ExpectedVersion"),
        ("cancel", "ReasonCommand"),
        ("complete", "ExpectedVersion"),
        ("resume", "ExpectedVersion"),
    ]:
        operation(
            "post",
            f"/requests/{{request_id}}/actions/{action}",
            action.replace("-", "_") + "_request",
            f"Действие заявки: {action}",
            "Request",
            body,
            requirements=["FR-03", "FR-11"],
            idempotent=True,
        )
    operation(
        "put",
        "/requests/{request_id}/selected-tour",
        "select_request_tour",
        "Записать выбор клиента",
        "Request",
        "SelectTour",
        requirements=["FR-04"],
        idempotent=True,
    )

    operation(
        "get",
        "/tours",
        "list_tours",
        "Тестовый каталог туров",
        "TourOfferPage",
        requirements=["FR-04"],
        paginated=True,
        sort=["price", "-price", "starts_on"],
        parameters=[
            query("destination", text_schema, "Часть направления без учёта регистра"),
            query(
                "starts_from", ref("Date"), "Начало тура не раньше даты, включительно"
            ),
            query(
                "ends_until", ref("Date"), "Окончание тура не позже даты, включительно"
            ),
            query(
                "tourist_count",
                {"type": "integer", "minimum": 1},
                "Точное число туристов",
            ),
            query("max_price", ref("Money"), "Максимальная общая цена в RUB"),
        ],
        description="Только активные предложения. Фильтры применяются совместно. Некорректный интервал дат: 422. Цена за всех туристов; отдельного экрана управления каталогом в MVP нет.",
    )
    operation(
        "get",
        "/tours/{tour_id}",
        "get_tour",
        "Карточка предложения",
        "TourOffer",
        requirements=["FR-04"],
        description="Активное предложение общего каталога доступно manager/head независимо от наличия заявок. Неактивный и отсутствующий тур дают одинаковый 404.",
    )
    operation(
        "get",
        "/requests/{request_id}/selections",
        "list_request_selections",
        "История подборок заявки",
        "SelectionPage",
        requirements=["FR-04"],
        paginated=True,
        sort=["-created_at"],
    )
    operation(
        "post",
        "/requests/{request_id}/selections",
        "create_selection",
        "Опубликовать подборку",
        "Selection",
        "SelectionCreate",
        requirements=["FR-04"],
        status=201,
        idempotent=True,
        description="version относится к заявке; >=1 уникального тура. Снимки и статус offer_prepared создаются транзакционно; прежний выбор сбрасывается, ссылки старых подборок отзываются. Ссылку затем выдаёт отдельная команда.",
    )
    operation(
        "get",
        "/selections/{selection_id}",
        "get_selection",
        "Подборка сотрудника",
        "Selection",
        requirements=["FR-04"],
    )
    operation(
        "post",
        "/selections/{selection_id}/public-link",
        "issue_selection_link",
        "Выдать или перевыпустить ссылку подборки",
        "PublicLink",
        requirements=["FR-04"],
        status=201,
        description="Выдаёт случайный токен на 7 дней, отзывает предыдущую ссылку этой подборки. В хранилище только хеш. Повтор создаёт новую ссылку; не повторять автоматически после сетевой ошибки. Скопировать url можно из ответа в текущей сессии интерфейса.",
    )
    operation(
        "post",
        "/requests/{request_id}/tourist-link",
        "issue_tourist_link",
        "Выдать или перевыпустить ссылку формы туристов",
        "PublicLink",
        requirements=["FR-10"],
        status=201,
        description="Только при редактируемой форме. Срок 7 дней, предыдущая ссылка отзывается. При неопределённом результате сети использовать явный перевыпуск, не слепой повтор.",
    )
    operation(
        "delete",
        "/public-links/{link_id}",
        "revoke_public_link",
        "Отозвать публичную ссылку",
        requirements=["FR-04", "FR-10"],
        status=204,
    )
    operation(
        "get",
        "/public/selections/{token}",
        "get_public_selection",
        "Открыть подборку без входа",
        "PublicSelection",
        roles=["public"],
        requirements=["FR-04"],
        description="Только снимки туров одной подборки. Нет клиента, ответственного, токена в ответе и паспортов. Неверный/просроченный/отозванный токен: одинаковый 404.",
    )
    operation(
        "get",
        "/public/tourist-forms/{token}",
        "get_public_tourist_form",
        "Открыть форму туристов без входа",
        "PublicTouristForm",
        roles=["public"],
        requirements=["FR-10"],
        description="Только число туристов, версия заявки, срок и редактируемость. Ранее введённые персональные данные не возвращаются. При действующей брони форма закрыта, is_editable=false и closed_reason заполнен.",
    )
    operation(
        "put",
        "/public/tourist-forms/{token}",
        "submit_public_tourists",
        "Передать полный список туристов",
        "TouristSubmissionResult",
        "TouristSubmission",
        roles=["public"],
        requirements=["FR-10"],
        idempotent=True,
        description="Атомарная замена полного списка, количество равно tourist_count. version проверяется по request_version. Новые туристы имеют id=null; переданный id обязан принадлежать этой заявке. После создания действующей брони: 409 tourist_form_closed.",
    )
    operation(
        "get",
        "/requests/{request_id}/tourists",
        "get_request_tourists",
        "Данные туристов для сотрудника",
        roles=STAFF,
        requirements=["FR-10"],
        description="Массив Tourist, без пагинации, только ответственный и руководитель.",
    )
    document["paths"]["/requests/{request_id}/tourists"]["get"]["responses"]["200"][
        "content"
    ] = {
        "application/json": {
            "schema": {"type": "array", "items": ref("Tourist")},
            "example": [examples["Tourist"]],
        }
    }
    operation(
        "put",
        "/requests/{request_id}/tourists",
        "replace_request_tourists",
        "Исправить список туристов сотрудником",
        "TouristSubmissionResult",
        "TouristSubmission",
        requirements=["FR-10"],
        idempotent=True,
    )

    operation(
        "get",
        "/requests/{request_id}/bookings",
        "list_request_bookings",
        "Попытки бронирования",
        "BookingPage",
        requirements=["FR-05", "FR-11"],
        paginated=True,
        sort=["-created_at"],
    )
    operation(
        "post",
        "/requests/{request_id}/bookings",
        "create_booking",
        "Создать попытку брони",
        "Booking",
        "ExpectedVersion",
        requirements=["FR-05"],
        status=201,
        idempotent=True,
        description="version относится к заявке; выбранный элемент берётся из заявки. Полный корректный список туристов обязателен уже при создании, число совпадает с заявкой и туром: после создания форма блокируется. Сумма и снимок назначаются сервером. Не более одной действующей брони.",
    )
    operation(
        "get",
        "/bookings/{booking_id}",
        "get_booking",
        "Карточка брони со снимками туристов",
        "Booking",
        requirements=["FR-05"],
    )
    booking_commands = [
        ("confirm", "ConfirmBooking"),
        ("reject", "ReasonCommand"),
        ("request-cancellation", "ReasonCommand"),
        ("confirm-cancellation", "ConfirmCancellation"),
        ("reject-cancellation", "ReasonCommand"),
    ]
    for action, body in booking_commands:
        operation(
            "post",
            f"/bookings/{{booking_id}}/actions/{action}",
            action.replace("-", "_") + "_booking",
            f"Действие брони: {action}",
            "Booking",
            body,
            requirements=["FR-05", "FR-11"],
            idempotent=True,
            description="version относится к брони. Сервер также блокирует заявку и проверяет условия из state-transitions.md; связанные статусы и аудит меняются транзакционно.",
        )

    financial_filters = [
        query("request_id", ref("Id"), "Идентификатор заявки"),
        query("booking_id", ref("Id"), "Идентификатор брони"),
    ]
    operation(
        "get",
        "/financial-bookings",
        "list_financial_bookings",
        "Финансовая сводка броней",
        "FinancialBookingPage",
        roles=FINANCE,
        requirements=["FR-06", "FR-08", "FR-12"],
        parameters=[
            query("request_id", ref("Id"), "Идентификатор заявки"),
            query("status", ref("BookingStatus"), "Статус брони"),
        ],
        paginated=True,
        sort=["-created_at"],
        description="Бухгалтер получает только суммы, статусы и идентификаторы, can_open_request=false. Полная Booking содержит туристов и бухгалтеру недоступна.",
    )
    operation(
        "get",
        "/payments",
        "list_payments",
        "Глобальный список оплат",
        "PaymentPage",
        roles=FINANCE,
        requirements=["FR-06", "FR-08"],
        parameters=[
            *financial_filters,
            query("status", ref("PaymentStatus"), "Статус платежа"),
        ],
        paginated=True,
        sort=["-created_at", "created_at"],
    )
    operation(
        "get",
        "/bookings/{booking_id}/payments",
        "list_booking_payments",
        "Оплаты конкретной брони",
        "PaymentPage",
        roles=ALL_STAFF,
        requirements=["FR-06"],
        paginated=True,
        sort=["-created_at"],
    )
    operation(
        "post",
        "/bookings/{booking_id}/payments",
        "create_payment",
        "Создать тестовый платёж",
        "Payment",
        "PaymentCreate",
        requirements=["FR-06"],
        status=202,
        idempotent=True,
        description="version относится к брони; amount <= available_payment_amount. Возвращает локальную pending-операцию; payment_url может быть null до ответа сервиса. Через GET или reconcile получить ссылку/результат. Сетевой тайм-аут сохраняет резерв и pending_reason.",
    )
    operation(
        "get",
        "/payments/{payment_id}",
        "get_payment",
        "Платёж и доступный остаток возврата",
        "Payment",
        roles=ALL_STAFF,
        requirements=["FR-06", "FR-12"],
    )
    operation(
        "post",
        "/payments/{payment_id}/reconcile",
        "reconcile_payment",
        "Сверить платёж с сервисом",
        "Payment",
        requirements=["FR-06"],
        status=202,
        description="Естественно повторяемая команда без ручного назначения успеха. Адаптер опрашивает известную операцию с тем же внешним ключом; терминальная операция возвращается без повторного зачисления. Бухгалтер имеет только GET.",
    )
    operation(
        "get",
        "/refunds",
        "list_refunds",
        "Глобальный список возвратов",
        "RefundPage",
        roles=FINANCE,
        requirements=["FR-12"],
        parameters=[
            *financial_filters,
            query("payment_id", ref("Id"), "Исходный платёж"),
            query("status", ref("RefundStatus"), "Статус возврата"),
        ],
        paginated=True,
        sort=["-created_at", "created_at"],
    )
    operation(
        "get",
        "/payments/{payment_id}/refunds",
        "list_payment_refunds",
        "Возвраты по платежу",
        "RefundPage",
        roles=ALL_STAFF,
        requirements=["FR-12"],
        paginated=True,
        sort=["-created_at"],
    )
    operation(
        "post",
        "/payments/{payment_id}/refunds",
        "create_refund",
        "Создать возврат",
        "Refund",
        "RefundCreate",
        requirements=["FR-12"],
        status=202,
        idempotent=True,
        description="Только по cancelled-брони и succeeded-платежу; amount <= available_refund_amount. Под блокировками резервируются processing суммы. Сотрудник не назначает статус сервиса.",
    )
    operation(
        "get",
        "/refunds/{refund_id}",
        "get_refund",
        "Состояние возврата",
        "Refund",
        roles=ALL_STAFF,
        requirements=["FR-12"],
    )
    operation(
        "post",
        "/refunds/{refund_id}/reconcile",
        "reconcile_refund",
        "Сверить возврат с сервисом",
        "Refund",
        requirements=["FR-12"],
        status=202,
        description="Естественно повторяемая команда. Только проверенный ответ сервиса завершает возврат; повтор не увеличивает возвращённую сумму.",
    )

    operation(
        "get",
        "/clients/{client_id}/communications",
        "list_client_communications",
        "История общения с клиентом",
        "CommunicationPage",
        requirements=["FR-07"],
        paginated=True,
        sort=["-occurred_at"],
        description="В карточке клиента выдаются записи без заявки и по доступным заявкам; записи чужих заявок исключены до пагинации и подсчёта total.",
    )
    operation(
        "post",
        "/clients/{client_id}/communications",
        "create_communication",
        "Записать контакт с клиентом",
        "Communication",
        "CommunicationCreate",
        requirements=["FR-07"],
        status=201,
        idempotent=True,
        description="Автор и created_at назначаются сервером; occurred_at передаёт время контакта. request_id=null либо доступная заявка этого клиента. Фактическая отправка сообщений отсутствует.",
    )
    operation(
        "get",
        "/requests/{request_id}/communications",
        "list_request_communications",
        "Общение по заявке",
        "CommunicationPage",
        requirements=["FR-07", "FR-08"],
        paginated=True,
        sort=["-occurred_at"],
    )
    operation(
        "get",
        "/requests/{request_id}/history",
        "list_request_history",
        "История статусов и ответственных",
        "AuditRecordPage",
        requirements=["FR-01", "FR-08"],
        paginated=True,
        sort=["-created_at"],
        description="Только белый список изменений: ответственный и статусы/суммы. Нет паспортов, хешей, токенов и произвольного внутреннего JSON аудита.",
    )
    operation(
        "get",
        "/notifications",
        "list_notifications",
        "Свои уведомления",
        "NotificationPage",
        requirements=["FR-13"],
        parameters=[
            query(
                "unread_only",
                {"type": "boolean", "default": False},
                "Только непрочитанные",
            )
        ],
        paginated=True,
        sort=["-created_at"],
        description="Только уведомления текущего сотрудника; unread_count по всем его непрочитанным, независимо от страницы. После переназначения недоступной заявки request_id=null, can_open_request=false. Базовый способ обновления UI — опрос раз в 15 секунд при активной вкладке.",
    )
    operation(
        "post",
        "/notifications/{notification_id}/read",
        "read_notification",
        "Отметить своё уведомление прочитанным",
        "Notification",
        requirements=["FR-13"],
        description="Естественно идемпотентно: read_at первого прочтения сохраняется. Другому получателю: 404.",
    )
    operation(
        "get",
        "/reports/summary",
        "get_summary_report",
        "Сводный отчёт за период",
        "Report",
        roles=["head"],
        requirements=["FR-08"],
        parameters=[
            query(
                "date_from",
                ref("Date"),
                "Первый календарный день Москвы, включительно",
                True,
            ),
            query(
                "date_to",
                ref("Date"),
                "Последний календарный день Москвы, включительно",
                True,
            ),
        ],
        description="date_to >= date_from. Интервал [начало date_from, начало дня после date_to) в Europe/Moscow. Заявки: created_at; брони: confirmed_at, включая позже отменённые; оплаты/возвраты: succeeded_at. Пустой период возвращает нули.",
    )

    # Explicit prefixes work identically in FastAPI exports, generated clients and Prism.
    document["paths"] = {
        "/api" + path: item for path, item in document["paths"].items()
    }
    # Domain definitions remain a standalone JSON Schema; the exported OpenAPI is self-contained.
    text = json.dumps(document, ensure_ascii=False, indent=2)
    return json.loads(text.replace("#/$defs/", "#/components/schemas/"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Fail if committed OpenAPI differs"
    )
    args = parser.parse_args()
    result = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    path = DIRECTORY / "openapi.json"
    if args.check:
        if not path.exists() or json.loads(
            path.read_text(encoding="utf-8")
        ) != json.loads(result):
            raise SystemExit("openapi.json is stale; run build_openapi.py")
        print("OpenAPI matches domain schemas, examples and operation registry.")
    else:
        path.write_text(result, encoding="utf-8")
        print(f"Written {path.name}")


if __name__ == "__main__":
    main()
