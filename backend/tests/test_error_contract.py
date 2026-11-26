from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import register_errors
from tests.test_clients import actors as actors
from tests.test_clients import validate
from tests.test_requests import payload as request_payload

SENTINEL = "PRIVATE-SENTINEL-INPUT-18"


@pytest.mark.parametrize(
    "status,code",
    [
        (400, "validation_error"),
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "not_found"),
        (405, "not_found"),
        (409, "conflict"),
        (422, "validation_error"),
        (429, "rate_limited"),
        (500, "server_error"),
        (501, "not_implemented"),
        (503, "server_error"),
    ],
)
def test_http_statuses_share_safe_contract(status, code):
    app = FastAPI()
    register_errors(app)

    @app.get("/probe")
    def probe():
        raise HTTPException(
            status,
            detail=SENTINEL,
            headers={"Allow": "GET", "Retry-After": "7", "X-Private": SENTINEL},
        )

    with TestClient(app) as connection:
        response = connection.get("/probe")
    assert response.status_code == status and response.json()["code"] == code
    validate("Error", response.json())
    assert response.json()["fields"] == [] and SENTINEL not in response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Allow"] == "GET" and response.headers["Retry-After"] == "7"
    assert "X-Private" not in response.headers
    if status == 401:
        assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "failure,status", [(ValueError(SENTINEL), 500), (SQLAlchemyError(SENTINEL), 503)]
)
def test_unexpected_and_database_errors_hide_details(failure, status):
    app = FastAPI()
    register_errors(app)

    @app.get("/probe")
    def probe():
        raise failure

    with TestClient(app, raise_server_exceptions=False) as connection:
        response = connection.get("/probe")
    assert response.status_code == status
    assert response.json()["code"] == "server_error" and SENTINEL not in response.text
    validate("Error", response.json())


@pytest.mark.parametrize(
    "field,value,fragment",
    [
        ("budget", "-1.00", "неотрицательную"),
        ("budget", 1, "строкой"),
        ("tourist_count", 0, "туристов"),
        ("tourist_count", True, "целое"),
        ("starts_on", "2026-02-30", "YYYY-MM-DD"),
        ("ends_on", "2020-01-01", "раньше"),
        ("destination", "  ", "пустым"),
        ("client_id", "not-a-uuid", "UUID"),
    ],
)
def test_request_rules_report_field_errors(client, actors, field, value, fragment):
    payload = request_payload(str(uuid4()), **{field: value})
    response = client.post(
        "/api/requests",
        json=payload,
        headers={**actors["manager"]["headers"], "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422
    validate("Error", response.json())
    errors = {item["field"]: item["message"] for item in response.json()["fields"]}
    assert field in errors and fragment in errors[field]


@pytest.mark.parametrize(
    "kind,payload,field,fragment",
    [
        (
            "payments",
            {"version": 1, "amount": "0.00", "currency": "RUB"},
            "amount",
            "положительную",
        ),
        ("payments", {"version": False, "amount": "1.00", "currency": "RUB"}, "version", "версию"),
        ("refunds", {"amount": "-1.00", "currency": "RUB"}, "amount", "положительную"),
        ("refunds", {"amount": "1.001", "currency": "RUB"}, "amount", "двумя"),
        ("refunds", {"amount": "1.00", "currency": "USD"}, "currency", "допустимое"),
    ],
)
def test_financial_commands_validate_without_frontend(
    client, actors, kind, payload, field, fragment
):
    path = (
        f"/api/bookings/{uuid4()}/payments"
        if kind == "payments"
        else f"/api/payments/{uuid4()}/refunds"
    )
    response = client.post(
        path,
        json=payload,
        headers={**actors["manager"]["headers"], "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422
    errors = {item["field"]: item["message"] for item in response.json()["fields"]}
    assert fragment in errors[field]


@pytest.mark.parametrize(
    "field,value",
    [("birth_date", "9999-12-31"), ("document_number", "  "), ("document_expires_on", None)],
)
def test_nested_tourist_fields_keep_index_without_input(client, actors, field, value):
    tourist = {
        "id": None,
        "full_name": SENTINEL,
        "birth_date": "1990-01-01",
        "document_type": "international_passport",
        "document_number": "FICTIONAL-18",
        "document_expires_on": "2030-01-01",
        field: value,
    }
    response = client.put(
        f"/api/requests/{uuid4()}/tourists",
        json={"request_version": 1, "tourists": [tourist]},
        headers={**actors["manager"]["headers"], "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422 and SENTINEL not in response.text
    assert f"tourists.0.{field}" in [item["field"] for item in response.json()["fields"]]


def test_unknown_fields_remain_unknown_and_invalid_json_is_body_error(client, actors):
    headers = {**actors["manager"]["headers"], "Idempotency-Key": str(uuid4())}
    payload = request_payload(str(uuid4()), amount="bad", phone=SENTINEL)
    result = client.post("/api/requests", json=payload, headers=headers)
    assert result.status_code == 422 and SENTINEL not in result.text
    errors = {item["field"]: item["message"] for item in result.json()["fields"]}
    assert errors["amount"] == errors["phone"] == "Неизвестное поле"
    broken = client.post(
        "/api/requests",
        content='{"secret":"' + SENTINEL + '",',
        headers={**headers, "Content-Type": "application/json"},
    )
    assert broken.status_code == 422 and SENTINEL not in broken.text
    assert broken.json()["fields"] == [{"field": "body", "message": "Передайте корректный JSON"}]


def test_missing_amount_stays_required_and_http_methods_keep_allow(client, actors):
    response = client.post(
        f"/api/payments/{uuid4()}/refunds",
        json={"currency": "RUB"},
        headers={**actors["manager"]["headers"], "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422
    assert {"field": "amount", "message": "Обязательное поле"} in response.json()["fields"]
    wrong_method = client.delete("/api/requests", headers=actors["manager"]["headers"])
    assert wrong_method.status_code == 405 and "Allow" in wrong_method.headers
    assert wrong_method.json()["code"] == "not_found"
