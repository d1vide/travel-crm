from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.core.audit import AuditRecord
from app.core.idempotency import IdempotencyRecord
from app.main import create_app
from app.modules.auth.models import User
from app.modules.requests.models import RequestStatus, TravelRequest
from tests.test_clients import actors as actors
from tests.test_clients import create as create_client
from tests.test_clients import validate


def payload(target_client_id, **changes):
    return {
        "client_id": target_client_id,
        "manager_id": None,
        "destination": "Сочи",
        "starts_on": "2027-06-01",
        "ends_on": "2027-06-08",
        "tourist_count": 2,
        "budget": "120000.00",
        "wishes": "Море",
        **changes,
    }


def write(client, actors, method, path, body, actor="manager", key=None):
    return client.request(
        method,
        path,
        json=body,
        headers={**actors[actor]["headers"], "Idempotency-Key": str(key or uuid4())},
    )


def create(client, actors, target_client_id, *, actor="manager", key=None, **changes):
    return write(
        client, actors, "POST", "/api/requests", payload(target_client_id, **changes), actor, key
    )


def action(client, actors, row, name, *, actor="manager", key=None, **body):
    return write(
        client,
        actors,
        "POST",
        f"/api/requests/{row['id']}/actions/{name}",
        {"version": row["version"], **body},
        actor,
        key,
    )


@pytest.fixture
def client_id(client, actors):
    return create_client(client, actors).json()["id"]


def test_create_card_and_history_match_contract(client, actors, client_id, database):
    response = create(client, actors, client_id)
    assert response.status_code == 201, response.text
    row = response.json()
    validate("Request", row)
    assert row["status"] == "new" and row["version"] == 1
    assert row["budget"] == "120000.00"
    assert row["manager"]["id"] == str(actors["manager"]["id"])
    assert row["client"]["id"] == client_id
    assert row["allowed_actions"] == ["update", "cancel", "start_work"]
    assert row["selected_offer"] is None and row["active_booking"] is None
    assert row["tourists_received"] == 0 and row["tourist_form_editable"] is False
    assert (
        client.get(f"/api/requests/{row['id']}", headers=actors["manager"]["headers"]).json() == row
    )
    history = client.get(f"/api/requests/{row['id']}/history", headers=actors["manager"]["headers"])
    assert history.status_code == 200
    validate("AuditRecordPage", history.json())
    assert history.json()["items"][0]["changes"] == [
        {"field": "request_status", "old_value": None, "new_value": "new"}
    ]
    assert "email" not in history.json()["items"][0]["actor"]
    with database.sessions() as session:
        assert session.get(TravelRequest, UUID(row["id"])).budget.as_tuple().exponent == -2


@pytest.mark.parametrize(
    "changes",
    [
        {"destination": " "},
        {"destination": 1},
        {"starts_on": "2027-02-30"},
        {"starts_on": "2027-06-01T00:00:00Z"},
        {"starts_on": 1},
        {"ends_on": "2027-05-31"},
        {"tourist_count": 0},
        {"tourist_count": True},
        {"tourist_count": "2"},
        {"tourist_count": 2**31},
        {"budget": 10.0},
        {"budget": "-1.00"},
        {"budget": "10.1"},
        {"budget": "01.00"},
        {"budget": "1000000000000.00"},
        {"wishes": "private\x00"},
        {"status": "booked"},
        {"version": 1},
        {"client_id": "invalid"},
        {"manager_id": "invalid"},
    ],
)
def test_invalid_command_is_atomic(client, actors, client_id, database, changes):
    response = create(client, actors, client_id, **changes)
    assert response.status_code == 422
    validate("Error", response.json())
    assert "private" not in response.text
    if "ends_on" in changes:
        assert response.json()["fields"] == [
            {"field": "ends_on", "message": "Дата окончания не может быть раньше начала"}
        ]
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(TravelRequest)) == 0
        assert session.scalar(select(func.count()).select_from(AuditRecord)) == 0
        assert (
            session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
        )  # client creation


def test_missing_key_and_manager_field(client, actors, client_id):
    body = payload(client_id)
    assert (
        client.post("/api/requests", json=body, headers=actors["manager"]["headers"]).status_code
        == 422
    )
    body.pop("manager_id")
    assert write(client, actors, "POST", "/api/requests", body).status_code == 422


def test_roles_and_directory(client, actors, client_id, database):
    row = create(client, actors, client_id).json()
    for actor, status in [("manager", 403), ("accountant", 403), ("head", 200)]:
        response = client.get("/api/users", headers=actors[actor]["headers"])
        assert response.status_code == status
        if status == 200:
            validate("UserPage", response.json())
            assert response.json()["total"] == 3
            assert all(
                set(user) == {"id", "full_name", "role"} for user in response.json()["items"]
            )
    with database.sessions.begin() as session:
        session.get(User, actors["other"]["id"]).is_active = False
    assert client.get("/api/users", headers=actors["head"]["headers"]).json()["total"] == 2
    for method, path, body in [
        ("GET", "/api/requests", None),
        ("POST", "/api/requests", payload(client_id)),
        ("GET", f"/api/requests/{row['id']}", None),
        (
            "PUT",
            f"/api/requests/{row['id']}",
            {
                "version": 1,
                **{
                    k: v
                    for k, v in payload(client_id).items()
                    if k not in ("client_id", "manager_id")
                },
            },
        ),
        ("GET", f"/api/requests/{row['id']}/history", None),
        ("POST", f"/api/requests/{row['id']}/actions/start-work", {"version": 1}),
        ("POST", f"/api/requests/{row['id']}/actions/cancel", {"version": 1, "reason": "Тест"}),
        ("POST", f"/api/requests/{row['id']}/actions/resume", {"version": 1}),
        (
            "PATCH",
            f"/api/requests/{row['id']}/assignee",
            {"version": 1, "manager_id": str(actors["head"]["id"])},
        ),
    ]:
        assert write(client, actors, method, path, body, actor="accountant").status_code == 403
        assert (
            client.request(
                method, path, json=body, headers={"Idempotency-Key": str(uuid4())}
            ).status_code
            == 401
        )


def test_assignee_validation(client, actors, client_id, database):
    assert (
        create(client, actors, client_id, manager_id=str(actors["other"]["id"])).status_code == 403
    )
    assert (
        create(
            client, actors, client_id, actor="head", manager_id=str(actors["accountant"]["id"])
        ).status_code
        == 422
    )
    assert (
        create(client, actors, client_id, actor="head", manager_id=str(uuid4())).status_code == 422
    )
    with database.sessions.begin() as session:
        session.get(User, actors["other"]["id"]).is_active = False
    assert (
        create(
            client, actors, client_id, actor="head", manager_id=str(actors["other"]["id"])
        ).status_code
        == 422
    )
    response = create(client, actors, client_id, actor="head")
    assert response.status_code == 201
    assert response.json()["manager_id"] == str(actors["head"]["id"])


def test_filters_and_no_hidden_counts(client, actors, client_id):
    own = create(client, actors, client_id).json()
    foreign = create(
        client, actors, client_id, actor="head", manager_id=str(actors["other"]["id"])
    ).json()
    own2 = create(client, actors, client_id, starts_on="2027-05-01").json()
    page = client.get("/api/requests", headers=actors["manager"]["headers"]).json()
    validate("RequestPage", page)
    assert page["total"] == 2 and {r["id"] for r in page["items"]} == {own["id"], own2["id"]}
    assert client.get("/api/requests", headers=actors["head"]["headers"]).json()["total"] == 3
    assert (
        client.get(
            "/api/requests",
            params={"manager_id": str(actors["other"]["id"])},
            headers=actors["manager"]["headers"],
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/requests/{foreign['id']}", headers=actors["manager"]["headers"]
        ).status_code
        == 404
    )
    for identity in (foreign["id"], str(uuid4())):
        assert (
            client.get(
                f"/api/requests/{identity}/history", headers=actors["manager"]["headers"]
            ).status_code
            == 404
        )
    filtered = client.get(
        "/api/requests",
        params={"client_id": client_id, "status": "new", "sort": "starts_on", "page_size": 1},
        headers=actors["manager"]["headers"],
    ).json()
    assert filtered["total"] == 2 and filtered["items"][0]["id"] == own2["id"]
    assert (
        client.get(
            "/api/requests", params={"page": 100}, headers=actors["manager"]["headers"]
        ).json()["items"]
        == []
    )


@pytest.mark.parametrize(
    "params",
    [
        {"status": "invalid"},
        {"unknown": "x"},
        {"page": 0},
        {"page_size": 101},
        {"sort": "wishes"},
        {"client_id": "invalid"},
        {"page": 10**30},
    ],
)
def test_invalid_filters(client, actors, params):
    response = client.get("/api/requests", params=params, headers=actors["manager"]["headers"])
    assert response.status_code == 422
    validate("Error", response.json())


def test_hidden_or_missing_client_cannot_be_used(client, actors, client_id):
    assert create(client, actors, str(uuid4())).status_code == 404
    assert create(client, actors, client_id, actor="other").status_code == 404
    assert (
        client.get(
            "/api/requests", params={"client_id": client_id}, headers=actors["other"]["headers"]
        ).status_code
        == 404
    )


def test_update_and_version_conflict(client, actors, client_id, database):
    row = create(client, actors, client_id).json()
    body = {k: v for k, v in payload(client_id).items() if k not in ("client_id", "manager_id")}
    body.update(version=1, budget="0.00", destination="Казань")
    result = write(client, actors, "PUT", f"/api/requests/{row['id']}", body)
    assert result.status_code == 200 and result.json()["version"] == 2
    assert result.json()["budget"] == "0.00"
    stale = write(client, actors, "PUT", f"/api/requests/{row['id']}", body)
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(AuditRecord)) == 1


def test_status_commands_and_history(client, actors, client_id):
    row = create(client, actors, client_id).json()
    invalid = action(client, actors, row, "resume")
    assert invalid.status_code == 409 and invalid.json()["code"] == "invalid_transition"
    assert action(client, actors, row, "cancel", reason=" ").status_code == 422
    row = action(client, actors, row, "start-work").json()
    assert row["status"] == "in_progress" and "start_work" not in row["allowed_actions"]
    row = action(client, actors, row, "cancel", reason="  Изменились планы  ").json()
    assert (
        row["status"] == "cancelled"
        and row["cancelled_at"]
        and row["cancellation_reason"] == "Изменились планы"
    )
    assert row["allowed_actions"] == ["resume"]
    row = action(client, actors, row, "resume").json()
    assert (
        row["status"] == "in_progress"
        and row["cancelled_at"] is None
        and row["cancellation_reason"] is None
    )
    history = client.get(
        f"/api/requests/{row['id']}/history", headers=actors["manager"]["headers"]
    ).json()
    assert history["total"] == 4
    validate("AuditRecordPage", history)
    assert {item["action"] for item in history["items"]} == {
        "created",
        "start-work",
        "cancel",
        "resume",
    }
    assert "Изменились планы" not in str(history)


@pytest.mark.parametrize(
    "status", [RequestStatus.OFFER_PREPARED, RequestStatus.BOOKED, RequestStatus.COMPLETED]
)
def test_future_states_are_not_editable_without_their_modules(
    client, actors, client_id, database, status
):
    row = create(client, actors, client_id).json()
    with database.sessions.begin() as session:
        session.get(TravelRequest, UUID(row["id"])).status = status
    for name, body in [("start-work", {}), ("cancel", {"reason": "Тест"}), ("resume", {})]:
        assert action(client, actors, row, name, **body).status_code == 409
    read = client.get(f"/api/requests/{row['id']}", headers=actors["manager"]["headers"]).json()
    assert read["allowed_actions"] == []


def test_reassignment_changes_access_and_audits_once(client, actors, client_id, database):
    create_key = uuid4()
    row = create(client, actors, client_id, key=create_key).json()
    path = f"/api/requests/{row['id']}/assignee"
    body = {"version": 1, "manager_id": str(actors["other"]["id"])}
    assert write(client, actors, "PATCH", path, body).status_code == 403
    key = uuid4()
    assigned = write(client, actors, "PATCH", path, body, actor="head", key=key)
    assert assigned.status_code == 200 and assigned.json()["version"] == 2
    assert (
        write(client, actors, "PATCH", path, body, actor="head", key=key).json() == assigned.json()
    )
    assert create(client, actors, client_id, key=create_key).status_code == 404
    for suffix in ("", "/history"):
        assert (
            client.get(
                f"/api/requests/{row['id']}{suffix}", headers=actors["manager"]["headers"]
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/requests/{row['id']}{suffix}", headers=actors["other"]["headers"]
            ).status_code
            == 200
        )
    assert (
        client.get(f"/api/clients/{client_id}", headers=actors["manager"]["headers"]).status_code
        == 404
    )
    with database.sessions() as session:
        records = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "assignee_changed")
        ).all()
        assert len(records) == 1 and records[0].actor_id == actors["head"]["id"]
        assert records[0].changes == [
            {
                "field": "manager_id",
                "old_value": str(actors["manager"]["id"]),
                "new_value": str(actors["other"]["id"]),
            }
        ]


def test_persistent_replay_and_payload_conflict(client, actors, client_id, settings):
    key = uuid4()
    row = create(client, actors, client_id, key=key).json()
    with TestClient(create_app(settings)) as restarted:
        retry = create(restarted, actors, client_id, key=key)
    assert retry.status_code == 201 and retry.json() == row
    conflict = create(client, actors, client_id, key=key, wishes="Другое тело")
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    key = uuid4()
    result = action(client, actors, row, "start-work", key=key)
    retry = action(client, actors, row, "start-work", key=key)
    assert result.status_code == retry.status_code == 200 and retry.json()["version"] == 2


@pytest.mark.parametrize("mode", ["same_key", "same_version", "reassign_and_edit"])
def test_parallel_commands(client, actors, client_id, settings, database, mode):
    row = create(client, actors, client_id).json() if mode != "same_key" else None
    barrier = Barrier(2)
    shared_key = uuid4()

    def run(index):
        with TestClient(create_app(settings)) as connection:
            barrier.wait(timeout=15)
            if mode == "same_key":
                return create(connection, actors, client_id, key=shared_key).status_code
            if mode == "same_version":
                return action(connection, actors, row, "start-work").status_code
            if index == 0:
                return write(
                    connection,
                    actors,
                    "PATCH",
                    f"/api/requests/{row['id']}/assignee",
                    {"version": 1, "manager_id": str(actors["other"]["id"])},
                    actor="head",
                ).status_code
            return action(connection, actors, row, "start-work").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(run, range(2)))
    assert statuses == ([201, 201] if mode == "same_key" else [200, 409]) or (
        mode == "reassign_and_edit" and statuses == [200, 404]
    )
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(TravelRequest)) == 1
        assert session.scalar(select(func.count()).select_from(AuditRecord)) == (
            1 if mode == "same_key" else 2
        )


def test_list_projects_names_without_per_row_queries(client, actors, client_id, application):
    for _ in range(4):
        assert create(client, actors, client_id).status_code == 201
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    engine = application.state.database.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/requests", headers=actors["manager"]["headers"])
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200 and len(response.json()["items"]) == 4
    assert len(statements) <= 5  # authentication, count, requests, clients, managers


def test_same_assignee_and_history_pagination(client, actors, client_id):
    row = create(client, actors, client_id).json()
    same = write(
        client,
        actors,
        "PATCH",
        f"/api/requests/{row['id']}/assignee",
        {"version": 1, "manager_id": str(actors["manager"]["id"])},
        actor="head",
    )
    assert same.status_code == 200 and same.json()["version"] == 1
    action(client, actors, row, "start-work")
    result = client.get(
        f"/api/requests/{row['id']}/history",
        params={"page_size": 1},
        headers=actors["head"]["headers"],
    ).json()
    assert result["total"] == 2 and len(result["items"]) == 1
    assert result["items"][0]["action"] == "start-work"
    assert (
        client.get("/api/users", params={"page_size": 1}, headers=actors["head"]["headers"]).json()[
            "total"
        ]
        == 3
    )
    assert (
        client.get(
            "/api/users", params={"email": "private"}, headers=actors["head"]["headers"]
        ).status_code
        == 422
    )
