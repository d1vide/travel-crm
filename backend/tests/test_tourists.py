import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier, Event
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from app.core.audit import AuditRecord
from app.core.idempotency import IdempotencyRecord
from app.core.public_links import PublicLink
from app.main import create_app
from app.modules.clients.models import Client
from app.modules.requests.models import RequestStatus, TravelRequest
from app.modules.tourists.models import Tourist
from app.modules.tourists.schemas import TouristSubmission
from tests.test_clients import actors as actors
from tests.test_clients import create as create_client
from tests.test_clients import validate
from tests.test_requests import action, write
from tests.test_requests import create as create_request
from tests.test_selections import publish, read_request


def item(**changes):
    return {
        "id": None,
        "full_name": "Вымышленный турист",
        "birth_date": "1995-05-20",
        "document_type": "passport",
        "document_number": "FICTIONAL-DOC-32-A",
        "document_expires_on": None,
        **changes,
    }


def body(request, tourists=None):
    return {
        "request_version": request["version"],
        "tourists": tourists
        if tourists is not None
        else [item(), item(document_number="FICTIONAL-DOC-32-B")],
    }


@pytest.fixture
def context(client, actors):
    client_id = create_client(client, actors).json()["id"]
    request = create_request(client, actors, client_id).json()
    return action(client, actors, request, "start-work").json()


def issue(client, actors, request, actor="manager"):
    return client.post(
        f"/api/requests/{request['id']}/tourist-link", headers=actors[actor]["headers"]
    )


def path(link):
    return "/api" + urlsplit(link["url"]).path


def submit(client, link, payload, key=None):
    return client.put(path(link), json=payload, headers={"Idempotency-Key": str(key or uuid4())})


def staff_list(client, actors, request, actor="manager"):
    return client.get(f"/api/requests/{request['id']}/tourists", headers=actors[actor]["headers"])


def staff_submit(client, actors, request, payload, actor="manager", key=None):
    return write(
        client, actors, "PUT", f"/api/requests/{request['id']}/tourists", payload, actor, key
    )


def assert_private(response):
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_public_submission_staff_read_and_projections(client, actors, context, database):
    request = context
    assert {"edit_tourists", "issue_tourist_link"} <= set(request["allowed_actions"])
    assert request["tourist_form_editable"] and request["tourist_link"] is None
    assert staff_list(client, actors, request).json() == []
    response = issue(client, actors, request)
    assert response.status_code == 201
    assert_private(response)
    link = response.json()
    validate("PublicLink", link)
    assert link["purpose"] == "tourists" and "/public/tourist-forms/" in link["url"]
    form = client.get(path(link))
    assert form.status_code == 200
    assert_private(form)
    validate("PublicTouristForm", form.json())
    assert set(form.json()) == {
        "tourist_count",
        "request_version",
        "expires_at",
        "is_editable",
        "closed_reason",
    }
    assert form.json()["is_editable"] and form.json()["closed_reason"] is None
    payload = body(request)
    response = submit(client, link, payload)
    assert response.status_code == 200
    assert_private(response)
    validate("TouristSubmissionResult", response.json())
    assert response.json() == {"accepted_count": 2, "request_version": 3}
    saved = staff_list(client, actors, request)
    assert_private(saved)
    assert len(saved.json()) == 2
    for tourist in saved.json():
        validate("Tourist", tourist)
        assert tourist["request_id"] == request["id"] and tourist["version"] == 1
    card = read_request(client, actors, request["id"])
    validate("Request", card)
    assert card["tourists_received"] == 2 and card["tourist_form_editable"]
    assert card["tourist_link"] == {
        "id": link["id"],
        "purpose": "tourists",
        "expires_at": link["expires_at"],
        "is_active": True,
    }
    public = client.get(path(link)).json()
    assert public["request_version"] == 3
    assert "FICTIONAL" not in json.dumps(public) and "Вымышленный" not in json.dumps(
        public, ensure_ascii=False
    )
    with database.sessions() as session:
        record = session.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.resource_type == "tourists")
        )
        assert record.result_metadata == response.json()
        persisted = json.dumps(
            {column.name: str(getattr(record, column.name)) for column in record.__table__.columns}
        )
        assert urlsplit(link["url"]).path.split("/")[-1] not in persisted
        assert "FICTIONAL" not in persisted
        assert session.scalar(select(func.count()).select_from(AuditRecord)) == 2


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"full_name": "  "}, "full_name"),
        ({"full_name": 12}, "full_name"),
        ({"full_name": "bad\x00name"}, "full_name"),
        ({"birth_date": "2999-01-01"}, "birth_date"),
        ({"birth_date": "2026-02-30"}, "birth_date"),
        ({"birth_date": "1995-05-20T00:00:00Z"}, "birth_date"),
        ({"birth_date": 123}, "birth_date"),
        ({"document_number": " "}, "document_number"),
        ({"document_number": 12345}, "document_number"),
        ({"document_type": "bank_card"}, "document_type"),
        ({"document_type": "international_passport"}, "document_expires_on"),
        ({"document_expires_on": "not-date"}, "document_expires_on"),
        ({"card_number": "FICTIONAL-CARD-DO-NOT-SAVE"}, "card_number"),
    ],
)
def test_invalid_fields_return_safe_indexed_errors(
    client, actors, context, database, changes, field
):
    link = issue(client, actors, context).json()
    payload = body(context, [item(), item(**changes)])
    response = submit(client, link, payload)
    assert response.status_code == 422
    assert_private(response)
    validate("Error", response.json())
    assert any(error["field"] == f"tourists.1.{field}" for error in response.json()["fields"])
    assert "FICTIONAL" not in response.text
    assert staff_list(client, actors, context).json() == []
    assert read_request(client, actors, context["id"])["version"] == context["version"]
    with database.sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(IdempotencyRecord.resource_type == "tourists")
            )
            == 0
        )


def test_complete_list_and_required_fields(client, actors, context):
    link = issue(client, actors, context).json()
    for tourists in ([], [item()], [item(), item(), item()]):
        response = submit(client, link, body(context, tourists))
        assert response.status_code == 422 and response.json()["fields"][0]["field"] == "tourists"
    for field in item():
        incomplete = item()
        del incomplete[field]
        response = submit(client, link, body(context, [incomplete, item()]))
        assert response.status_code == 422
        assert response.json()["fields"][0]["field"] == f"tourists.0.{field}"
    payload = body(context)
    payload["request_version"] = True
    assert submit(client, link, payload).status_code == 422
    assert client.put(path(link), json=body(context)).status_code == 422


def test_staff_replace_order_versions_and_retired_ids(client, actors, context, database):
    payload = body(
        context,
        [
            item(full_name="  Вымышленный турист  ", document_number="  TEST-32  "),
            item(document_type="international_passport", document_expires_on="2031-05-20"),
        ],
    )
    assert staff_submit(client, actors, context, payload, actor="head").status_code == 200
    first = staff_list(client, actors, context).json()
    assert (
        first[0]["full_name"] == "Вымышленный турист" and first[0]["document_number"] == "TEST-32"
    )
    current = read_request(client, actors, context["id"])
    retained = {field: first[1][field] for field in item()}
    response = staff_submit(
        client,
        actors,
        context,
        body(current, [retained, item(full_name="Другой вымышленный турист")]),
    )
    assert response.status_code == 200
    second = staff_list(client, actors, context).json()
    assert second[0]["id"] == first[1]["id"] and second[0]["version"] == 2
    assert second[1]["id"] not in {tourist["id"] for tourist in first}
    with database.sessions() as session:
        assert session.get(Tourist, UUID(first[0]["id"])).removed_at is not None
        assert session.scalar(select(func.count()).select_from(Tourist)) == 3
    current = read_request(client, actors, context["id"])
    retired = {field: first[0][field] for field in item()}
    assert (
        staff_submit(client, actors, context, body(current, [retired, item()])).status_code == 404
    )
    assert staff_list(client, actors, context).json() == second


def test_foreign_duplicate_and_unknown_ids_are_atomic(client, actors, context):
    assert staff_submit(client, actors, context, body(context)).status_code == 200
    saved = staff_list(client, actors, context).json()
    current = read_request(client, actors, context["id"])
    original = {field: saved[0][field] for field in item()}
    duplicate = staff_submit(client, actors, context, body(current, [original, original]))
    assert duplicate.status_code == 422 and duplicate.json()["fields"][0]["field"] == "tourists"
    other = create_request(client, actors, context["client_id"]).json()
    other = action(client, actors, other, "start-work").json()
    assert staff_submit(client, actors, other, body(other)).status_code == 200
    foreign = staff_list(client, actors, other).json()[0]["id"]
    for identity in (foreign, str(uuid4())):
        result = staff_submit(client, actors, context, body(current, [item(id=identity), item()]))
        assert result.status_code == 404
    assert staff_list(client, actors, context).json() == saved
    assert read_request(client, actors, context["id"])["version"] == current["version"]


def test_persistent_replay_safe_metadata_and_current_permissions(client, actors, context, settings):
    link = issue(client, actors, context).json()
    payload, key = body(context), uuid4()
    first = submit(client, link, payload, key)
    assert first.status_code == 200
    current = read_request(client, actors, context["id"])
    assert staff_submit(client, actors, context, body(current)).status_code == 200
    with TestClient(create_app(settings)) as connection:
        repeat = submit(connection, link, payload, key)
    assert repeat.json() == first.json()
    changed = body(context, [item(full_name="Иное имя"), item()])
    assert submit(client, link, changed, key).json()["code"] == "idempotency_conflict"
    assert submit(client, link, payload).json()["code"] == "version_conflict"
    assert (
        client.delete(
            f"/api/public-links/{link['id']}", headers=actors["manager"]["headers"]
        ).status_code
        == 204
    )
    assert submit(client, link, payload, key).status_code == 404


def test_staff_reassignment_denies_old_access_and_replay(client, actors, context):
    key, payload = uuid4(), body(context)
    first = staff_submit(client, actors, context, payload, key=key)
    assert first.status_code == 200
    link = issue(client, actors, context).json()
    current = read_request(client, actors, context["id"])
    moved = write(
        client,
        actors,
        "PATCH",
        f"/api/requests/{context['id']}/assignee",
        {"version": current["version"], "manager_id": str(actors["other"]["id"])},
        "head",
    )
    assert moved.status_code == 200
    assert staff_list(client, actors, context).status_code == 404
    assert staff_submit(client, actors, context, payload, key=key).status_code == 404
    assert issue(client, actors, context).status_code == 404
    assert len(staff_list(client, actors, context, "other").json()) == 2
    assert client.get(path(link)).status_code == 200
    assert submit(client, link, body(moved.json())).status_code == 200


def test_staff_roles_and_hidden_resources(client, actors, context):
    for actor, expected in (("other", 404), ("accountant", 403)):
        assert staff_list(client, actors, context, actor).status_code == expected
        assert staff_submit(client, actors, context, body(context), actor).status_code == expected
        assert issue(client, actors, context, actor).status_code == expected
    hidden = staff_list(client, actors, context, "other")
    missing = staff_list(client, actors, {"id": str(uuid4())})
    assert hidden.json() == missing.json()
    assert client.get(f"/api/requests/{context['id']}/tourists").status_code == 401


@pytest.mark.parametrize(
    "status",
    [RequestStatus.NEW, RequestStatus.BOOKED, RequestStatus.COMPLETED, RequestStatus.CANCELLED],
)
def test_closed_form_and_private_commands(client, actors, context, database, status):
    link = issue(client, actors, context).json()
    with database.sessions.begin() as session:
        session.get(TravelRequest, UUID(context["id"])).status = status
    form = client.get(path(link))
    assert (
        form.status_code == 200 and not form.json()["is_editable"] and form.json()["closed_reason"]
    )
    result = submit(client, link, body(context))
    assert result.status_code == 409 and result.json()["code"] == "tourist_form_closed"
    assert issue(client, actors, context).status_code == 409
    assert staff_submit(client, actors, context, body(context)).status_code == 409
    assert staff_list(client, actors, context).json() == []
    card = read_request(client, actors, context["id"])
    assert not card["tourist_form_editable"]
    assert not {"edit_tourists", "issue_tourist_link"} & set(card["allowed_actions"])


def test_rotation_expiry_purpose_and_uniform_404(client, actors, context, database):
    first = issue(client, actors, context).json()
    second = issue(client, actors, context).json()
    with database.sessions.begin() as session:
        row = session.get(PublicLink, UUID(second["id"]))
        assert row.expires_at - row.created_at == timedelta(days=7)
        assert row.token_hash != urlsplit(second["url"]).path.split("/")[-1]
        row.created_at = datetime.now(UTC) - timedelta(days=8)
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    failures = [
        first,
        second,
        {"url": "http://localhost/public/tourist-forms/bad"},
        {"url": "http://localhost/public/tourist-forms/" + "A" * 43},
    ]
    for link in failures:
        response = client.get(path(link))
        assert response.status_code == 404
        assert response.json() == {"code": "not_found", "message": "Форма недоступна", "fields": []}
        assert_private(response)
        assert submit(client, link, body(context)).status_code == 404
    active = issue(client, actors, context).json()
    token = path(active).split("/")[-1]
    assert client.get("/api/public/selections/" + token).status_code == 404
    response = client.delete(f"/api/public-links/{active['id']}", headers=actors["head"]["headers"])
    assert response.status_code == 204 and client.get(path(active)).status_code == 404


def test_cancel_resume_return_and_selection_replacement(client, actors, context, database):
    from app.modules.tours.models import TourOffer

    link = issue(client, actors, context).json()
    with database.sessions() as session:
        offer_id = str(session.scalar(select(TourOffer.id).limit(1)))
    selection = publish(client, actors, context, [offer_id])
    assert selection.status_code == 201 and client.get(path(link)).status_code == 200
    current = read_request(client, actors, context["id"])
    assert action(client, actors, current, "return-to-work").status_code == 200
    assert client.get(path(link)).status_code == 404
    current = read_request(client, actors, context["id"])
    link = issue(client, actors, current).json()
    assert staff_submit(client, actors, current, body(current)).status_code == 200
    current = read_request(client, actors, context["id"])
    cancelled = action(client, actors, current, "cancel", reason="Вымышленная отмена").json()
    assert client.get(path(link)).status_code == 404
    assert cancelled["tourists_received"] == 2 and not cancelled["tourist_link"]["is_active"]
    resumed = action(client, actors, cancelled, "resume").json()
    assert resumed["tourist_form_editable"] and resumed["tourists_received"] == 2
    assert client.get(path(link)).status_code == 404


@pytest.mark.parametrize("mode", ["same_key", "different_keys", "rotate", "cancel"])
def test_concurrent_submissions(client, actors, context, settings, database, mode):
    link, key, barrier = issue(client, actors, context).json(), uuid4(), Barrier(2)
    payload = body(context)

    def run(index):
        with TestClient(create_app(settings)) as connection:
            barrier.wait(timeout=15)
            if index == 1 and mode == "rotate":
                return issue(connection, actors, context)
            if index == 1 and mode == "cancel":
                return action(connection, actors, context, "cancel", reason="Учебная отмена")
            return submit(connection, link, payload, key if mode == "same_key" else uuid4())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    if mode == "same_key":
        assert [response.status_code for response in results] == [200, 200]
        assert results[0].json() == results[1].json()
    elif mode == "different_keys":
        assert sorted(response.status_code for response in results) == [200, 409]
    elif mode == "rotate":
        assert results[0].status_code in (200, 404) and results[1].status_code == 201
    else:
        assert [response.status_code for response in results] in ([200, 409], [404, 200])
    with database.sessions() as session:
        count = session.scalar(
            select(func.count()).select_from(Tourist).where(Tourist.removed_at.is_(None))
        )
        assert count == (2 if results[0].status_code == 200 or mode == "different_keys" else 0)


def test_database_constraints_and_safe_repr(client, actors, context, database):
    assert "FICTIONAL" not in repr(TouristSubmission.model_validate(body(context)))
    base = {
        **item(),
        "request_id": UUID(context["id"]),
        "position": 0,
        "version": 1,
        "birth_date": date(1995, 5, 20),
    }
    del base["id"]
    for changes in (
        {"document_type": "card"},
        {"document_type": "international_passport"},
        {"full_name": " "},
        {"document_number": " "},
        {"birth_date": date(2999, 1, 1)},
        {"position": -1},
        {"version": 0},
        {"request_id": uuid4()},
    ):
        with pytest.raises(IntegrityError), database.sessions.begin() as session:
            session.add(Tourist(**{**base, **changes}))
            session.flush()


def test_batched_request_projection(client, actors, context, application):
    link = issue(client, actors, context).json()
    assert submit(client, link, body(context)).status_code == 200
    statements = []

    def capture(_connection, _cursor, statement, *_args):
        statements.append(statement)

    engine = application.state.database.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/requests", headers=actors["manager"]["headers"])
        assert response.status_code == 200 and len(statements) <= 9
        row = response.json()["items"][0]
        assert row["tourists_received"] == 2 and row["tourist_link"]["is_active"]
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_replay_after_form_closes_and_new_command_is_denied(client, actors, context, database):
    link, key, payload = issue(client, actors, context).json(), uuid4(), body(context)
    first = submit(client, link, payload, key)
    assert first.status_code == 200
    with database.sessions.begin() as session:
        session.get(TravelRequest, UUID(context["id"])).status = RequestStatus.BOOKED
    assert submit(client, link, payload, key).json() == first.json()
    assert submit(client, link, payload).json()["code"] == "tourist_form_closed"


@pytest.mark.parametrize("mode", ["revoke", "expire"])
def test_public_link_is_rechecked_after_waiting_for_parent_lock(
    client, actors, context, database, settings, mode
):
    link, waiting = issue(client, actors, context).json(), Event()

    def run():
        application = create_app(settings)

        def capture(_connection, _cursor, statement, *_args):
            if "FROM clients" in statement and "FOR UPDATE" in statement:
                waiting.set()

        event.listen(application.state.database.engine, "before_cursor_execute", capture)
        with TestClient(application) as connection:
            return submit(connection, link, body(context))

    with ThreadPoolExecutor(max_workers=1) as pool:
        with database.sessions.begin() as session:
            session.scalar(
                select(Client).where(Client.id == UUID(context["client_id"])).with_for_update()
            )
            future = pool.submit(run)
            assert waiting.wait(timeout=15)
            row = session.get(PublicLink, UUID(link["id"]))
            if mode == "revoke":
                row.revoked_at = datetime.now(UTC)
            else:
                row.created_at = datetime.now(UTC) - timedelta(days=8)
                row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        response = future.result(timeout=15)
    assert response.status_code == 404
    assert staff_list(client, actors, context).json() == []


def test_form_uses_latest_count_and_version(client, actors, context):
    link = issue(client, actors, context).json()
    update = {
        field: context[field]
        for field in (
            "version",
            "destination",
            "starts_on",
            "ends_on",
            "tourist_count",
            "budget",
            "wishes",
        )
    }
    update["tourist_count"] = 3
    response = write(client, actors, "PUT", f"/api/requests/{context['id']}", update)
    assert response.status_code == 200
    current = response.json()
    form = client.get(path(link)).json()
    assert form["request_version"] == current["version"] and form["tourist_count"] == 3
    assert submit(client, link, body(context)).json()["code"] == "version_conflict"
    assert submit(client, link, body(current)).status_code == 422
    assert submit(client, link, body(current, [item(), item(), item()])).status_code == 200
