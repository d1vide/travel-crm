import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.idempotency import IdempotencyRecord
from app.main import create_app
from app.modules.auth.models import User
from app.modules.clients.models import Client
from app.modules.communications.models import Communication, CommunicationChannel
from app.modules.requests.models import TravelRequest
from tests.test_clients import actors as actors
from tests.test_clients import create as create_client
from tests.test_clients import payload as client_payload
from tests.test_clients import validate
from tests.test_requests import create as create_request
from tests.test_requests import write


def payload(**changes):
    return {
        "request_id": None,
        "channel": "phone",
        "text": "Обсудили пожелания",
        "occurred_at": "2026-11-15T09:00:00Z",
        **changes,
    }


def create(client, actors, client_id, *, actor="manager", key=None, **changes):
    return write(
        client,
        actors,
        "POST",
        f"/api/clients/{client_id}/communications",
        payload(**changes),
        actor,
        key,
    )


@pytest.fixture
def context(client, actors):
    client_id = create_client(client, actors).json()["id"]
    request_id = create_request(client, actors, client_id).json()["id"]
    return client_id, request_id


def test_create_and_both_lists_follow_contract(client, actors, context, database):
    client_id, request_id = context
    result = create(
        client,
        actors,
        client_id,
        request_id=request_id,
        text="  Обсудили пожелания\nВторая строка  ",
    )
    assert result.status_code == 201, result.text
    row = result.json()
    validate("Communication", row)
    assert row["author_id"] == str(actors["manager"]["id"]) == row["author"]["id"]
    assert set(row["author"]) == {"id", "full_name", "role"}
    assert row["text"] == "Обсудили пожелания\nВторая строка"
    assert row["created_at"] != row["occurred_at"] and row["created_at"].endswith("Z")
    for path in (
        f"/api/clients/{client_id}/communications",
        f"/api/requests/{request_id}/communications",
    ):
        response = client.get(path, headers=actors["manager"]["headers"])
        assert response.status_code == 200
        validate("CommunicationPage", response.json())
        assert response.json()["total"] == 1 and response.json()["items"] == [row]
    with database.sessions() as session:
        assert session.get(Client, UUID(client_id)).version == 1
        assert session.get(TravelRequest, UUID(request_id)).version == 1


@pytest.mark.parametrize("channel", ["phone", "email", "messenger", "office", "other"])
def test_supported_channels(client, actors, context, channel):
    result = create(
        client, actors, context[0], channel=channel, occurred_at="2026-11-15T09:00:00.123456Z"
    )
    assert result.status_code == 201
    assert result.json()["channel"] == channel
    assert result.json()["occurred_at"] == "2026-11-15T09:00:00.123456Z"


@pytest.mark.parametrize(
    "changes",
    [
        {"channel": "sms"},
        {"channel": 1},
        {"text": ""},
        {"text": " \n\t "},
        {"text": 42},
        {"text": "private-fixture\x00"},
        {"text": "private-fixture\ud800"},
        {"occurred_at": "2026-02-30T09:00:00Z"},
        {"occurred_at": "2026-11-15"},
        {"occurred_at": "2026-11-15T09:00:00"},
        {"occurred_at": "2026-11-15T12:00:00+03:00"},
        {"occurred_at": "2026-11-15T09:00:00+00:00"},
        {"occurred_at": 123},
        {"occurred_at": None},
        {"request_id": "invalid"},
        {"author_id": str(uuid4())},
        {"created_at": "2026-01-01T00:00:00Z"},
        {"client_id": str(uuid4())},
        {"version": 1},
    ],
)
def test_invalid_body_is_sanitized_and_atomic(client, actors, context, database, changes):
    response = client.post(
        f"/api/clients/{context[0]}/communications",
        content=json.dumps(payload(**changes), ensure_ascii=True),
        headers={
            **actors["manager"]["headers"],
            "Idempotency-Key": str(uuid4()),
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 422
    validate("Error", response.json())
    assert "private-fixture" not in response.text
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Communication)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(IdempotencyRecord.resource_type == "communication")
            )
            == 0
        )


def test_missing_fields_and_key(client, actors, context):
    path = f"/api/clients/{context[0]}/communications"
    assert (
        client.post(path, json=payload(), headers=actors["manager"]["headers"]).status_code == 422
    )
    for field in ("request_id", "channel", "text", "occurred_at"):
        body = payload()
        body.pop(field)
        assert write(client, actors, "POST", path, body).status_code == 422


def test_authentication_and_accountant_denied(client, actors, context):
    paths = (
        f"/api/clients/{context[0]}/communications",
        f"/api/requests/{context[1]}/communications",
    )
    for path in paths:
        assert client.get(path).status_code == 401
        assert client.get(path, headers=actors["accountant"]["headers"]).status_code == 403
    assert create(client, actors, context[0], actor="accountant").status_code == 403
    assert (
        client.post(paths[0], json=payload(), headers={"Idempotency-Key": str(uuid4())}).status_code
        == 401
    )


def test_client_feed_excludes_foreign_requests_before_count_and_page(client, actors, context):
    client_id, own_id = context
    other_id = create_request(
        client, actors, client_id, actor="head", manager_id=str(actors["other"]["id"])
    ).json()["id"]
    general = create(
        client, actors, client_id, actor="head", occurred_at="2026-11-15T08:00:00Z"
    ).json()
    own = create(
        client, actors, client_id, request_id=own_id, occurred_at="2026-11-15T09:00:00Z"
    ).json()
    foreign = create(
        client,
        actors,
        client_id,
        actor="other",
        request_id=other_id,
        occurred_at="2026-11-15T10:00:00Z",
    ).json()
    for actor, identities in [
        ("manager", {general["id"], own["id"]}),
        ("other", {general["id"], foreign["id"]}),
        ("head", {general["id"], own["id"], foreign["id"]}),
    ]:
        page = client.get(
            f"/api/clients/{client_id}/communications", headers=actors[actor]["headers"]
        ).json()
        assert (
            page["total"] == len(identities) and {row["id"] for row in page["items"]} == identities
        )
    page = client.get(
        f"/api/clients/{client_id}/communications",
        params={"page_size": 1},
        headers=actors["manager"]["headers"],
    ).json()
    assert page["total"] == 2 and page["items"][0]["id"] == own["id"]
    page = client.get(
        f"/api/requests/{own_id}/communications", headers=actors["manager"]["headers"]
    ).json()
    assert [row["id"] for row in page["items"]] == [own["id"]]
    assert create(client, actors, client_id, request_id=other_id).status_code == 404


def test_missing_hidden_and_mismatched_parents(client, actors, context):
    client_id, request_id = context
    other_client = create_client(
        client, actors, body=client_payload(phone=None, email="other-client@example.com")
    ).json()["id"]
    assert create(client, actors, other_client, request_id=request_id).status_code == 422
    assert create(client, actors, client_id, request_id=str(uuid4())).status_code == 404
    for identity in (client_id, str(uuid4())):
        response = client.get(
            f"/api/clients/{identity}/communications", headers=actors["other"]["headers"]
        )
        assert response.status_code == 404
        assert create(client, actors, identity, actor="other").status_code == 404
    for identity in (request_id, str(uuid4())):
        assert (
            client.get(
                f"/api/requests/{identity}/communications", headers=actors["other"]["headers"]
            ).status_code
            == 404
        )


def test_orphan_records_follow_client_access_after_first_request(client, actors):
    client_id = create_client(client, actors).json()["id"]
    key = uuid4()
    row = create(client, actors, client_id, key=key).json()
    assert (
        create_request(
            client, actors, client_id, actor="head", manager_id=str(actors["other"]["id"])
        ).status_code
        == 201
    )
    assert create(client, actors, client_id, key=key).status_code == 404
    assert (
        client.get(
            f"/api/clients/{client_id}/communications", headers=actors["manager"]["headers"]
        ).status_code
        == 404
    )
    page = client.get(
        f"/api/clients/{client_id}/communications", headers=actors["other"]["headers"]
    ).json()
    assert page["items"] == [row]


def test_reassignment_hides_cached_record_even_if_client_stays_visible(client, actors, context):
    client_id, request_id = context
    create_request(client, actors, client_id)
    key = uuid4()
    row = create(client, actors, client_id, request_id=request_id, key=key).json()
    assigned = write(
        client,
        actors,
        "PATCH",
        f"/api/requests/{request_id}/assignee",
        {"version": 1, "manager_id": str(actors["other"]["id"])},
        actor="head",
    )
    assert assigned.status_code == 200
    assert (
        client.get(f"/api/clients/{client_id}", headers=actors["manager"]["headers"]).status_code
        == 200
    )
    assert create(client, actors, client_id, request_id=request_id, key=key).status_code == 404
    assert (
        create(
            client, actors, client_id, request_id=request_id, key=key, text="Другое тело"
        ).status_code
        == 404
    )
    page = client.get(
        f"/api/clients/{client_id}/communications", headers=actors["manager"]["headers"]
    ).json()
    assert page["total"] == 0 and page["items"] == []
    page = client.get(
        f"/api/requests/{request_id}/communications", headers=actors["other"]["headers"]
    ).json()
    assert page["items"] == [row] and page["items"][0]["author_id"] == str(actors["manager"]["id"])


def test_persistent_replay_scope_and_body_conflict(client, actors, context, settings, database):
    client_id, _ = context
    key = uuid4()
    first = create(client, actors, client_id, key=key)
    with TestClient(create_app(settings)) as restarted:
        repeated = create(restarted, actors, client_id, key=key)
    assert first.status_code == repeated.status_code == 201 and first.json() == repeated.json()
    conflict = create(client, actors, client_id, key=key, text="Другая запись")
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    assert create(client, actors, client_id, actor="head", key=key).status_code == 201
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Communication)) == 2


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": 10**30},
        {"page_size": 101},
        {"sort": "created_at"},
        {"author_id": str(uuid4())},
    ],
)
def test_invalid_queries(client, actors, context, params):
    for path in (
        f"/api/clients/{context[0]}/communications",
        f"/api/requests/{context[1]}/communications",
    ):
        result = client.get(path, params=params, headers=actors["manager"]["headers"])
        assert result.status_code == 422
        validate("Error", result.json())


def test_stable_time_sort_empty_page_and_bulk_authors(
    client, actors, context, database, application
):
    with database.sessions.begin() as session:
        for identity in (UUID(int=2), UUID(int=3), UUID(int=1)):
            session.add(
                Communication(
                    id=identity,
                    client_id=UUID(context[0]),
                    request_id=None,
                    author_id=actors["manager"]["id"],
                    channel=CommunicationChannel.PHONE,
                    text="Вымышленный контакт",
                    occurred_at=datetime.fromisoformat("2026-11-15T09:00:00Z"),
                )
            )
    path = f"/api/clients/{context[0]}/communications"
    pages = [
        client.get(
            path, params={"page": page, "page_size": 1}, headers=actors["manager"]["headers"]
        ).json()
        for page in (1, 2, 3)
    ]
    assert [page["items"][0]["id"] for page in pages] == [str(UUID(int=i)) for i in (3, 2, 1)]
    empty = client.get(path, params={"page": 100}, headers=actors["manager"]["headers"]).json()
    assert empty["items"] == [] and empty["total"] == 3
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    engine = application.state.database.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = client.get(path, headers=actors["manager"]["headers"])
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert result.status_code == 200 and len(result.json()["items"]) == 3 and len(statements) <= 5


def test_database_rejects_cross_client_reference_and_invalid_fields(
    client, actors, context, database
):
    other_id = create_client(
        client, actors, body=client_payload(phone=None, email="second@example.com")
    ).json()["id"]
    for changes in (
        {"client_id": UUID(other_id)},
        {"channel": "invented"},
        {"text": " "},
        {"author_id": uuid4()},
    ):
        with pytest.raises(IntegrityError), database.sessions.begin() as session:
            values = {
                "client_id": UUID(context[0]),
                "request_id": UUID(context[1]),
                "author_id": actors["manager"]["id"],
                "channel": CommunicationChannel.PHONE,
                "text": "Вымышленная запись",
                "occurred_at": datetime.fromisoformat("2026-11-15T09:00:00Z"),
                **changes,
            }
            session.add(Communication(**values))
            session.flush()


def test_inactive_author_is_retained_and_records_cannot_be_edited(
    client, actors, context, database
):
    row = create(client, actors, context[0]).json()
    with database.sessions.begin() as session:
        session.get(User, actors["manager"]["id"]).is_active = False
    page = client.get(
        f"/api/clients/{context[0]}/communications", headers=actors["head"]["headers"]
    ).json()
    assert page["items"][0]["author"] == row["author"]
    assert (
        client.put(
            f"/api/clients/{context[0]}/communications", json={}, headers=actors["head"]["headers"]
        ).status_code
        == 405
    )
    assert (
        client.post(
            f"/api/requests/{context[1]}/communications",
            json=payload(),
            headers=actors["head"]["headers"],
        ).status_code
        == 405
    )


@pytest.mark.parametrize("mode", ["same_key", "different_keys", "reassign"])
def test_concurrent_creation_and_reassignment(client, actors, context, settings, database, mode):
    key = uuid4()
    barrier = Barrier(2)

    def run(index):
        with TestClient(create_app(settings)) as connection:
            barrier.wait(timeout=15)
            if mode == "reassign" and index == 1:
                return write(
                    connection,
                    actors,
                    "PATCH",
                    f"/api/requests/{context[1]}/assignee",
                    {"version": 1, "manager_id": str(actors["other"]["id"])},
                    actor="head",
                )
            return create(
                connection,
                actors,
                context[0],
                request_id=context[1],
                key=key if mode == "same_key" else uuid4(),
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    if mode == "reassign":
        assert results[1].status_code == 200 and results[0].status_code in (201, 404)
        expected = 1 if results[0].status_code == 201 else 0
    else:
        assert all(result.status_code == 201 for result in results)
        expected = 1 if mode == "same_key" else 2
        if mode == "same_key":
            assert results[0].json() == results[1].json()
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Communication)) == expected
        assert (
            session.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(IdempotencyRecord.resource_type == "communication")
            )
            == expected
        )


def test_orphan_record_rechecks_access_after_waiting_for_client_lock(
    client, actors, context, settings, database
):
    def create_after_lock():
        with TestClient(create_app(settings)) as connection:
            return create(connection, actors, context[0])

    with ThreadPoolExecutor(max_workers=1) as pool:
        with database.sessions.begin() as transaction:
            transaction.scalar(
                select(Client).where(Client.id == UUID(context[0])).with_for_update()
            )
            request = transaction.get(TravelRequest, UUID(context[1]))
            request.manager_id = actors["other"]["id"]
            transaction.flush()
            future = pool.submit(create_after_lock)
            deadline = monotonic() + 10
            while True:
                with database.engine.connect() as monitor:
                    blocked = monitor.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                            "WHERE datname = current_database() AND wait_event_type = 'Lock' "
                            "AND query LIKE '%FOR UPDATE OF clients%')"
                        )
                    )
                if blocked:
                    break
                if monotonic() >= deadline:
                    raise AssertionError("Communication did not reach the parent lock")
                sleep(0.01)
        response = future.result(timeout=10)
    assert response.status_code == 404
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Communication)) == 0
