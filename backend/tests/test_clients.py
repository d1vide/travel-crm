import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import func, select

from app.core.idempotency import IdempotencyRecord
from app.main import create_app
from app.modules.auth.models import Role, User
from app.modules.auth.security import password_hasher
from app.modules.clients.models import Client
from app.modules.requests.models import RequestStatus, TravelRequest
from tests.conftest import DEMO_PASSWORD
from tests.test_foundation import DOMAIN


def payload(**changes):
    return {
        "full_name": "Иван Иванов",
        "phone": "+7 (999) 000-00-01",
        "email": None,
        "preferences": "Море",
        "note": "Вымышленные данные",
        "duplicate_acknowledged": False,
        **changes,
    }


@pytest.fixture
def actors(database, login):
    with database.sessions.begin() as session:
        session.add(
            User(
                full_name="Другой менеджер",
                email="other@example.com",
                role=Role.MANAGER,
                password_hash=password_hasher.hash(DEMO_PASSWORD),
            )
        )
    with database.sessions() as session:
        ids = {user.email: user.id for user in session.scalars(select(User))}
    return {
        name: {
            "id": ids[email],
            "headers": {"Authorization": "Bearer " + login(email).json()["access_token"]},
        }
        for name, email in {
            "manager": "manager@example.com",
            "other": "other@example.com",
            "head": "head@example.com",
            "accountant": "accountant@example.com",
        }.items()
    }


def create(client, actors, actor="manager", *, body=None, key=None):
    return client.post(
        "/api/clients",
        json=body if body is not None else payload(),
        headers={**actors[actor]["headers"], "Idempotency-Key": str(key or uuid4())},
    )


def edit(client, actors, client_id, body, *, actor="manager", key=None):
    return client.put(
        f"/api/clients/{client_id}",
        json=body,
        headers={**actors[actor]["headers"], "Idempotency-Key": str(key or uuid4())},
    )


def assign(database, client_id, manager_id, status=RequestStatus.NEW):
    with database.sessions.begin() as session:
        request = TravelRequest(
            client_id=UUID(str(client_id)),
            manager_id=manager_id,
            destination="Сочи",
            starts_on=date(2027, 6, 1),
            ends_on=date(2027, 6, 8),
            tourist_count=2,
            budget=Decimal("100000.00"),
            status=status,
        )
        session.add(request)
        session.flush()
        return request.id


def validate(name, value):
    Draft202012Validator(
        {"$ref": f"#/$defs/{name}", "$defs": DOMAIN["$defs"]}, format_checker=FormatChecker()
    ).validate(value)


def test_create_read_update_contract(client, actors, database):
    response = create(
        client, actors, body=payload(full_name="  Иван   Иванов  ", email=" IVAN@EXAMPLE.COM ")
    )
    assert response.status_code == 201
    first = response.json()
    validate("Client", first)
    assert first["full_name"] == "Иван Иванов" and first["email"] == "ivan@example.com"
    assert first["version"] == 1 and first["client_number"] > 0
    assert first["allowed_actions"] == ["update", "create_request"]
    assert "created_by_id" not in first and "phone_normalized" not in first
    assert (
        client.get(f"/api/clients/{first['id']}", headers=actors["manager"]["headers"]).json()
        == first
    )
    response = edit(client, actors, first["id"], {**payload(note="Изменено"), "version": 1})
    assert response.status_code == 200 and response.json()["version"] == 2
    assert (
        response.json()["note"] == "Изменено"
        and response.json()["client_number"] == first["client_number"]
    )
    validate("Client", response.json())
    with database.sessions() as session:
        stored = session.get(Client, UUID(first["id"]))
        assert stored.created_by_id == actors["manager"]["id"]
        assert stored.phone_normalized == "+79990000001"


@pytest.mark.parametrize(
    "body,field",
    [
        (payload(phone=None, email=None), "phone"),
        (payload(phone=" ", email=" "), "email"),
        (payload(full_name=" \t "), "full_name"),
        (payload(phone="123"), "phone"),
        (payload(phone="+7 999 000-00-01 доб.12"), "phone"),
        (payload(email="invalid"), "email"),
        (payload(duplicate_acknowledged="false"), "duplicate_acknowledged"),
        (payload(note=42), "note"),
        (payload(note="private-fixture\x00"), "note"),
        (payload(full_name="\ud800"), "full_name"),
        (payload(created_by_id=str(uuid4())), "created_by_id"),
        (payload(client_number=100), "client_number"),
    ],
)
def test_invalid_input_never_writes_or_echoes_private_text(client, actors, database, body, field):
    response = client.post(
        "/api/clients",
        content=json.dumps(body, ensure_ascii=True),
        headers={
            **actors["manager"]["headers"],
            "Idempotency-Key": str(uuid4()),
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 422
    validate("Error", response.json())
    assert field in {error["field"] for error in response.json()["fields"]}
    assert "private-fixture" not in response.text
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Client)) == 0
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0


@pytest.mark.parametrize("key", [None, "invalid"])
def test_idempotency_header_required(client, actors, key):
    headers = dict(actors["manager"]["headers"])
    if key is not None:
        headers["Idempotency-Key"] = key
    response = client.post("/api/clients", json=payload(), headers=headers)
    assert response.status_code == 422


def test_wrong_content_type_is_validation_error(client, actors):
    response = client.post(
        "/api/clients",
        content="full_name=test",
        headers={
            **actors["manager"]["headers"],
            "Idempotency-Key": str(uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    assert response.status_code == 422
    validate("Error", response.json())


def test_missing_access_and_accountant_denied(client, actors):
    identity = str(uuid4())
    for method, path, body in [
        ("get", "/api/clients", None),
        ("get", "/api/clients/duplicates?phone=%2B79990000001", None),
        ("get", f"/api/clients/{identity}", None),
        ("post", "/api/clients", payload()),
        ("put", f"/api/clients/{identity}", {**payload(), "version": 1}),
    ]:
        for actor, status in [(None, 401), ("accountant", 403)]:
            headers = {
                "Idempotency-Key": str(uuid4()),
                **(actors[actor]["headers"] if actor else {}),
            }
            response = client.request(method, path, json=body, headers=headers)
            assert response.status_code == status


def test_visibility_before_first_request_and_no_hidden_totals(client, actors):
    mine = create(client, actors).json()
    hidden = create(
        client, actors, "head", body=payload(full_name="Скрытый клиент", phone="+79990000002")
    ).json()
    result = client.get("/api/clients", headers=actors["manager"]["headers"]).json()
    assert result["total"] == 1 and [row["id"] for row in result["items"]] == [mine["id"]]
    assert client.get("/api/clients", headers=actors["head"]["headers"]).json()["total"] == 2
    for identity in (hidden["id"], str(uuid4())):
        response = client.get(f"/api/clients/{identity}", headers=actors["manager"]["headers"])
        assert response.status_code == 404 and response.json() == {
            "code": "not_found",
            "message": "Клиент не найден",
            "fields": [],
        }
    assert (
        client.get(
            "/api/clients", params={"q": "Скрытый"}, headers=actors["manager"]["headers"]
        ).json()["total"]
        == 0
    )


def test_visibility_follows_assignments_and_reassignment(client, actors, database):
    customer = create(client, actors).json()
    request_id = assign(database, customer["id"], actors["other"]["id"])
    assert (
        client.get(
            f"/api/clients/{customer['id']}", headers=actors["manager"]["headers"]
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/clients/{customer['id']}", headers=actors["other"]["headers"]).status_code
        == 200
    )
    with database.sessions.begin() as session:
        session.get(TravelRequest, request_id).manager_id = actors["manager"]["id"]
    assert (
        client.get(
            f"/api/clients/{customer['id']}", headers=actors["manager"]["headers"]
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/clients/{customer['id']}", headers=actors["other"]["headers"]).status_code
        == 404
    )
    assign(database, customer["id"], actors["other"]["id"], status=RequestStatus.CANCELLED)
    assert (
        client.get(f"/api/clients/{customer['id']}", headers=actors["other"]["headers"]).status_code
        == 200
    )


def test_hidden_update_and_replay_are_denied(client, actors, database):
    key = uuid4()
    original_body = payload()
    customer = create(client, actors, body=original_body, key=key).json()
    update_key = uuid4()
    update_body = {**payload(note="Первое изменение"), "version": 1}
    assert edit(client, actors, customer["id"], update_body, key=update_key).status_code == 200
    assign(database, customer["id"], actors["other"]["id"])
    assert create(client, actors, body=original_body, key=key).status_code == 404
    assert edit(client, actors, customer["id"], update_body, key=update_key).status_code == 404
    assert (
        edit(
            client, actors, customer["id"], {**payload(note="Нельзя изменить"), "version": 2}
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/clients/{customer['id']}", headers=actors["head"]["headers"]).json()[
            "note"
        ]
        == "Первое изменение"
    )


def test_duplicates_normalize_contacts_and_require_acknowledgement(client, actors):
    original = create(client, actors, body=payload(email="IVAN@EXAMPLE.COM")).json()
    result = client.get(
        "/api/clients/duplicates",
        params={"phone": "8 (999) 000-00-01", "email": "ivan@example.com"},
        headers=actors["manager"]["headers"],
    )
    assert result.status_code == 200
    validate("DuplicateCheckResult", result.json())
    assert [item["id"] for item in result.json()["matches"]] == [original["id"]]
    assert result.json()["requires_head_review"] is False
    duplicate = create(client, actors, body=payload(phone="89990000001", email="ivan@example.com"))
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "duplicate_contacts"
    accepted = create(
        client,
        actors,
        body=payload(full_name="Родственник", phone="89990000001", duplicate_acknowledged=True),
    )
    assert accepted.status_code == 201 and accepted.json()["id"] != original["id"]
    assert accepted.json()["client_number"] != original["client_number"]


def test_hidden_duplicate_never_exposes_identity_or_allows_manager_bypass(client, actors):
    hidden = create(client, actors, "head", body=payload(full_name="Скрытый клиент")).json()
    result = client.get(
        "/api/clients/duplicates",
        params={"phone": "+79990000001"},
        headers=actors["manager"]["headers"],
    )
    assert result.json() == {"matches": [], "requires_head_review": True}
    assert hidden["id"] not in result.text and "Скрытый" not in result.text
    for acknowledged in (False, True):
        response = create(client, actors, body=payload(duplicate_acknowledged=acknowledged))
        assert (
            response.status_code == 409
            and response.json()["code"] == "duplicate_requires_head_review"
        )
    head_result = client.get(
        "/api/clients/duplicates",
        params={"phone": "+79990000001"},
        headers=actors["head"]["headers"],
    ).json()
    assert head_result["requires_head_review"] is False and len(head_result["matches"]) == 1
    assert (
        create(client, actors, "head", body=payload(duplicate_acknowledged=True)).status_code == 201
    )


def test_excluding_own_duplicate_and_hidden_exclude_id(client, actors):
    mine = create(client, actors).json()
    other = create(client, actors, "other", body=payload(phone="+79990000002")).json()
    result = client.get(
        "/api/clients/duplicates",
        params={"phone": "+79990000001", "exclude_client_id": mine["id"]},
        headers=actors["manager"]["headers"],
    )
    assert result.status_code == 200 and result.json() == {
        "matches": [],
        "requires_head_review": False,
    }
    assert (
        client.get(
            "/api/clients/duplicates",
            params={"phone": "+79990000001", "exclude_client_id": other["id"]},
            headers=actors["manager"]["headers"],
        ).status_code
        == 404
    )


def test_update_checks_new_contacts_and_preserves_unchanged_shared_contact(client, actors):
    first = create(client, actors).json()
    second = create(client, actors, body=payload(phone="+79990000002")).json()
    body = {**payload(phone="89990000001"), "version": 1}
    denied = edit(client, actors, second["id"], body)
    assert denied.status_code == 409 and denied.json()["code"] == "duplicate_contacts"
    accepted = edit(client, actors, second["id"], {**body, "duplicate_acknowledged": True})
    assert accepted.status_code == 200
    assert (
        edit(
            client, actors, first["id"], {**payload(note="Только примечание"), "version": 1}
        ).status_code
        == 200
    )


def test_persistent_idempotency_and_optimistic_version(client, actors, settings, database):
    key = uuid4()
    body = payload()
    first = create(client, actors, key=key, body=body)
    with TestClient(create_app(settings)) as restarted:
        second = create(restarted, actors, key=key, body=dict(reversed(list(body.items()))))
    assert first.status_code == second.status_code == 201 and first.json() == second.json()
    changed = create(client, actors, key=key, body=payload(full_name="Изменённое тело"))
    assert changed.status_code == 409 and changed.json()["code"] == "idempotency_conflict"
    identity = first.json()["id"]
    update_key = uuid4()
    update_body = {**payload(note="Обновлено"), "version": 1}
    first_update = edit(client, actors, identity, update_body, key=update_key)
    retry = edit(client, actors, identity, update_body, key=update_key)
    assert first_update.status_code == retry.status_code == 200 and retry.json()["version"] == 2
    stale = edit(client, actors, identity, {**payload(note="Старая версия"), "version": 1})
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Client)) == 1
        records = session.scalars(select(IdempotencyRecord)).all()
        assert len(records) == 2 and all(len(record.request_hash) == 64 for record in records)


@pytest.mark.parametrize(
    "query", ["ФЕДОР", "фёдоров", "IVAN@EXAMPLE.COM", "8 (999) 000-00-01", "999000", "7999"]
)
def test_search_name_email_and_formatted_phone(client, actors, query):
    item = create(
        client, actors, body=payload(full_name="Фёдоров Иван", email="ivan@example.com")
    ).json()
    response = client.get("/api/clients", params={"q": query}, headers=actors["manager"]["headers"])
    assert response.status_code == 200 and response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == item["id"]
    validate("ClientPage", response.json())


def test_literal_wildcards_pagination_and_stable_order(client, actors):
    first = create(
        client, actors, body=payload(full_name="Клиент %_", phone=None, email="first@example.com")
    ).json()
    create(
        client,
        actors,
        body=payload(full_name="Другой клиент", phone=None, email="second@example.com"),
    )
    result = client.get(
        "/api/clients", params={"q": "%_"}, headers=actors["manager"]["headers"]
    ).json()
    assert [item["id"] for item in result["items"]] == [first["id"]]
    page = client.get(
        "/api/clients",
        params={"page": 1, "page_size": 1, "sort": "client_number"},
        headers=actors["manager"]["headers"],
    ).json()
    assert page["total"] == 2 and page["items"][0]["id"] == first["id"]
    empty = client.get(
        "/api/clients", params={"page": 100, "page_size": 1}, headers=actors["manager"]["headers"]
    ).json()
    assert empty["items"] == [] and empty["total"] == 2


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page_size": 101},
        {"page": 10**30},
        {"sort": "password_hash"},
        {"unknown": "field"},
        {"q": " "},
    ],
)
def test_invalid_query_is_422(client, actors, params):
    response = client.get("/api/clients", params=params, headers=actors["manager"]["headers"])
    assert response.status_code == 422
    validate("Error", response.json())


def test_invalid_duplicate_query_and_no_delete(client, actors):
    for params in (
        {},
        {"phone": "invalid"},
        {"email": "invalid"},
        {"phone": "+79990000001", "extra": "x"},
    ):
        assert (
            client.get(
                "/api/clients/duplicates", params=params, headers=actors["manager"]["headers"]
            ).status_code
            == 422
        )
    identity = create(client, actors).json()["id"]
    assert (
        client.delete(f"/api/clients/{identity}", headers=actors["manager"]["headers"]).status_code
        == 405
    )
    assert (
        client.get(f"/api/clients/{identity}", headers=actors["manager"]["headers"]).status_code
        == 200
    )


@pytest.mark.parametrize("mode", ["same_key", "same_contact", "same_version"])
def test_parallel_writes_are_serialized(client, actors, settings, database, mode):
    identity = create(client, actors).json()["id"] if mode == "same_version" else None
    shared_key = uuid4()
    barrier = Barrier(2)

    def write(index):
        with TestClient(create_app(settings)) as connection:
            barrier.wait(timeout=10)
            if mode == "same_version":
                response = edit(
                    connection,
                    actors,
                    identity,
                    {**payload(note=f"Изменение {index}"), "version": 1},
                )
            else:
                response = create(
                    connection, actors, key=shared_key if mode == "same_key" else uuid4()
                )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(write, range(2)))
    assert sorted(status for status, _body in results) == (
        [201, 201] if mode == "same_key" else [200, 409] if mode == "same_version" else [201, 409]
    )
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Client)) == 1
        if mode == "same_version":
            assert session.get(Client, UUID(identity)).version == 2
        else:
            assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
