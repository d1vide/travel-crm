import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from uvicorn.protocols.utils import get_path_with_query_string

from app.core.config import Settings
from app.core.idempotency import IdempotencyRecord
from app.core.public_links import PublicLink, new_token, token_hash
from app.core.public_privacy import PublicResponsePrivacy
from app.main import create_app
from app.modules.requests.models import RequestStatus, TravelRequest
from app.modules.tours import selection_views
from app.modules.tours.models import TourOffer
from app.modules.tours.selection_models import Selection, SelectionItem
from tests.test_clients import actors as actors
from tests.test_clients import create as create_client
from tests.test_clients import validate
from tests.test_requests import action, write
from tests.test_requests import create as create_request


@pytest.fixture
def context(client, actors, database):
    client_id = create_client(client, actors).json()["id"]
    row = create_request(client, actors, client_id).json()
    row = action(client, actors, row, "start-work").json()
    with database.sessions() as session:
        ids = [
            str(identity)
            for identity in session.scalars(select(TourOffer.id).order_by(TourOffer.id).limit(2))
        ]
    return row, ids


def publish(client, actors, row, ids, *, actor="manager", key=None):
    return write(
        client,
        actors,
        "POST",
        f"/api/requests/{row['id']}/selections",
        {"version": row["version"], "tour_offer_ids": ids},
        actor,
        key,
    )


def issue(client, actors, selection, actor="manager"):
    return client.post(
        f"/api/selections/{selection['id']}/public-link", headers=actors[actor]["headers"]
    )


def public_path(link):
    return "/api" + urlsplit(link["url"]).path


def read_request(client, actors, identity, actor="manager"):
    return client.get(f"/api/requests/{identity}", headers=actors[actor]["headers"]).json()


def test_latest_selection_uses_publication_time_not_transaction_start(
    client, actors, context, database
):
    request, ids = context
    with database.sessions() as older_transaction:
        older_transaction.scalar(select(func.now()))
        first = publish(client, actors, request, ids).json()
        # A command may have started before another publisher acquired the request lock.
        later = Selection(
            request_id=UUID(request["id"]),
            created_by_id=actors["manager"]["id"],
        )
        older_transaction.add(later)
        older_transaction.flush()
        assert later.created_at > datetime.fromisoformat(first["created_at"].replace("Z", "+00:00"))
        assert selection_views.latest_ids(older_transaction, [later.request_id]) == {
            later.request_id: later.id
        }


def test_publish_list_card_choose_and_frozen_contract(client, actors, context):
    request, ids = context
    result = publish(client, actors, request, list(reversed(ids)))
    assert result.status_code == 201, result.text
    selection = result.json()
    validate("Selection", selection)
    assert [item["tour_offer_id"] for item in selection["items"]] == list(reversed(ids))
    assert [item["position"] for item in selection["items"]] == [0, 1]
    assert selection["public_link"] is None
    assert (
        client.get(
            f"/api/selections/{selection['id']}", headers=actors["manager"]["headers"]
        ).json()
        == selection
    )
    page = client.get(
        f"/api/requests/{request['id']}/selections", headers=actors["manager"]["headers"]
    ).json()
    validate("SelectionPage", page)
    assert page["items"] == [selection] and page["total"] == 1
    request = read_request(client, actors, request["id"])
    assert request["version"] == 3 and request["status"] == "offer_prepared"
    assert {"prepare_selection", "select_tour", "return_to_work", "cancel"} <= set(
        request["allowed_actions"]
    )
    item = selection["items"][0]
    path = f"/api/requests/{request['id']}/selected-tour"
    key = uuid4()
    body = {"version": 3, "selection_item_id": item["id"]}
    selected = write(client, actors, "PUT", path, body, key=key)
    assert selected.status_code == 200
    request = selected.json()
    validate("Request", request)
    assert request["version"] == 4 and request["selected_selection_item_id"] == item["id"]
    assert (
        request["selected_selection_id"] == selection["id"]
        and request["selected_offer"] == item["offer_snapshot"]
    )
    assert write(client, actors, "PUT", path, body, key=key).json() == request
    assert write(client, actors, "PUT", path, {**body, "version": 4}).json()["version"] == 4


@pytest.mark.parametrize(
    "changes",
    [
        {"tour_offer_ids": []},
        {"tour_offer_ids": ["invalid"]},
        {"version": 0},
        {"version": True},
        {"version": "2"},
        {"status": "booked"},
        {"created_by_id": str(uuid4())},
    ],
)
def test_invalid_commands_are_atomic(client, actors, context, database, changes):
    request, ids = context
    body = {"version": request["version"], "tour_offer_ids": ids, **changes}
    response = write(client, actors, "POST", f"/api/requests/{request['id']}/selections", body)
    assert response.status_code == 422
    validate("Error", response.json())
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Selection)) == 0
        assert session.scalar(select(func.count()).select_from(SelectionItem)) == 0
        assert session.get(TravelRequest, UUID(request["id"])).version == 2


def test_missing_fields_duplicates_inactive_and_unknown_offers(client, actors, context, database):
    request, ids = context
    path = f"/api/requests/{request['id']}/selections"
    assert (
        client.post(
            path, json={"version": 2, "tour_offer_ids": ids}, headers=actors["manager"]["headers"]
        ).status_code
        == 422
    )
    assert write(client, actors, "POST", path, {"version": 2}).status_code == 422
    assert publish(client, actors, request, [ids[0], ids[0]]).status_code == 422
    assert publish(client, actors, request, [ids[0], str(uuid4())]).status_code == 404
    with database.sessions.begin() as session:
        session.get(TourOffer, UUID(ids[0])).is_active = False
    assert publish(client, actors, request, ids).status_code == 404
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Selection)) == 0
        assert session.get(TravelRequest, UUID(request["id"])).status == RequestStatus.IN_PROGRESS


@pytest.mark.parametrize(
    "status",
    [RequestStatus.NEW, RequestStatus.CANCELLED, RequestStatus.BOOKED, RequestStatus.COMPLETED],
)
def test_publication_requires_editable_request_state(client, actors, context, database, status):
    request, ids = context
    with database.sessions.begin() as session:
        session.get(TravelRequest, UUID(request["id"])).status = status
    result = publish(client, actors, request, ids)
    assert result.status_code == 409 and result.json()["code"] == "invalid_transition"


def test_public_page_and_token_storage_are_minimal(client, actors, context, database):
    request, ids = context
    selection = publish(client, actors, request, ids).json()
    response = issue(client, actors, selection)
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    link = response.json()
    validate("PublicLink", link)
    token = urlsplit(link["url"]).path.rsplit("/", 1)[-1]
    assert len(token) == 43 and token_hash(token) == hashlib.sha256(token.encode()).hexdigest()
    page = client.get(public_path(link), headers={"Authorization": "Bearer invalid"})
    assert page.status_code == 200
    assert (
        page.headers["cache-control"] == "no-store"
        and page.headers["referrer-policy"] == "no-referrer"
    )
    validate("PublicSelection", page.json())
    assert set(page.json()) == {"items", "expires_at"}
    assert all(set(item) == {"id", "offer_snapshot"} for item in page.json()["items"])
    assert [item["offer_snapshot"] for item in page.json()["items"]] == [
        item["offer_snapshot"] for item in selection["items"]
    ]
    with database.sessions() as session:
        stored = session.get(PublicLink, UUID(link["id"]))
        assert stored.token_hash == token_hash(token) and token not in str(stored.__dict__)
        assert stored.expires_at - stored.created_at == timedelta(days=7)
        assert (
            "url" not in PublicLink.__table__.columns
            and "token" not in PublicLink.__table__.columns
        )
        assert all(
            record.result_metadata is None for record in session.scalars(select(IdempotencyRecord))
        )
    staff = client.get(
        f"/api/selections/{selection['id']}", headers=actors["manager"]["headers"]
    ).json()
    validate("Selection", staff)
    assert staff["public_link"]["is_active"] is True and "url" not in staff["public_link"]


def test_snapshot_is_unchanged_after_catalogue_mutation(client, actors, context, database):
    request, ids = context
    selection = publish(client, actors, request, ids).json()
    link = issue(client, actors, selection).json()
    original = client.get(public_path(link)).json()
    with database.sessions.begin() as session:
        row = session.get(TourOffer, UUID(ids[0]))
        row.price = Decimal("999.99")
        row.title = "Новое название"
        row.services = ["Другой состав"]
        row.is_active = False
    assert client.get(public_path(link)).json() == original
    request = read_request(client, actors, request["id"])
    selected = write(
        client,
        actors,
        "PUT",
        f"/api/requests/{request['id']}/selected-tour",
        {"version": request["version"], "selection_item_id": selection["items"][0]["id"]},
    ).json()
    assert selected["selected_offer"] == selection["items"][0]["offer_snapshot"]


def test_link_rotation_expiry_revocation_and_uniform_404(client, actors, context, database):
    request, ids = context
    selection = publish(client, actors, request, ids).json()
    first = issue(client, actors, selection).json()
    second = issue(client, actors, selection).json()
    assert first["url"] != second["url"]
    assert client.get(public_path(first)).status_code == 404
    assert client.get(public_path(second)).status_code == 200
    with database.sessions.begin() as session:
        stored = session.get(PublicLink, UUID(second["id"]))
        now = datetime.now(UTC)
        stored.created_at = now - timedelta(days=8)
        stored.expires_at = now - timedelta(days=1)
    expired = client.get(public_path(second))
    unknown = client.get("/api/public/selections/" + new_token()[0])
    malformed = client.get("/api/public/selections/invalid")
    assert expired.status_code == unknown.status_code == malformed.status_code == 404
    assert expired.json() == unknown.json() == malformed.json()
    for response in (expired, unknown, malformed):
        assert (
            response.headers["cache-control"] == "no-store"
            and response.headers["referrer-policy"] == "no-referrer"
        )
    third = issue(client, actors, selection).json()
    for _ in range(2):
        assert (
            client.delete(
                f"/api/public-links/{third['id']}", headers=actors["manager"]["headers"]
            ).status_code
            == 204
        )
    assert client.get(public_path(third)).status_code == 404


def test_replacement_and_return_to_work_revoke_links_and_reset_choice(client, actors, context):
    request, ids = context
    first = publish(client, actors, request, ids).json()
    link = issue(client, actors, first).json()
    request = write(
        client,
        actors,
        "PUT",
        f"/api/requests/{request['id']}/selected-tour",
        {"version": 3, "selection_item_id": first["items"][0]["id"]},
    ).json()
    second = publish(client, actors, request, [ids[1]]).json()
    request = read_request(client, actors, request["id"])
    assert request["version"] == 5 and request["selected_offer"] is None
    assert client.get(public_path(link)).status_code == 404
    assert issue(client, actors, first).status_code == 409
    assert (
        write(
            client,
            actors,
            "PUT",
            f"/api/requests/{request['id']}/selected-tour",
            {"version": 5, "selection_item_id": first["items"][0]["id"]},
        ).status_code
        == 409
    )
    second_link = issue(client, actors, second).json()
    returned = action(client, actors, request, "return-to-work")
    assert returned.status_code == 200 and returned.json()["status"] == "in_progress"
    assert returned.json()["version"] == 6 and returned.json()["selected_selection_item_id"] is None
    assert client.get(public_path(second_link)).status_code == 404
    assert issue(client, actors, second).status_code == 409
    assert publish(client, actors, returned.json(), ids).status_code == 201


def test_cancel_and_resume_clear_public_access(client, actors, context):
    request, ids = context
    selection = publish(client, actors, request, ids).json()
    link = issue(client, actors, selection).json()
    request = read_request(client, actors, request["id"])
    cancelled = action(client, actors, request, "cancel", reason="Изменились планы")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert client.get(public_path(link)).status_code == 404
    resumed = action(client, actors, cancelled.json(), "resume")
    assert resumed.status_code == 200 and resumed.json()["selected_offer"] is None


def test_private_roles_scope_and_missing_resources(client, actors, context):
    request, ids = context
    selection = publish(client, actors, request, ids).json()
    link = issue(client, actors, selection).json()
    routes = [
        ("GET", f"/api/requests/{request['id']}/selections", None),
        (
            "POST",
            f"/api/requests/{request['id']}/selections",
            {"version": 3, "tour_offer_ids": ids},
        ),
        ("GET", f"/api/selections/{selection['id']}", None),
        ("POST", f"/api/selections/{selection['id']}/public-link", None),
        ("DELETE", f"/api/public-links/{link['id']}", None),
        (
            "PUT",
            f"/api/requests/{request['id']}/selected-tour",
            {"version": 3, "selection_item_id": selection["items"][0]["id"]},
        ),
        ("POST", f"/api/requests/{request['id']}/actions/return-to-work", {"version": 3}),
    ]
    for method, path, body in routes:
        assert write(client, actors, method, path, body, actor="accountant").status_code == 403
        assert write(client, actors, method, path, body, actor="other").status_code == 404
        assert (
            client.request(
                method, path, json=body, headers={"Idempotency-Key": str(uuid4())}
            ).status_code
            == 401
        )
    hidden = client.get(f"/api/selections/{selection['id']}", headers=actors["other"]["headers"])
    missing = client.get(f"/api/selections/{uuid4()}", headers=actors["other"]["headers"])
    assert hidden.json() == missing.json()
    hidden = client.delete(f"/api/public-links/{link['id']}", headers=actors["other"]["headers"])
    missing = client.delete(f"/api/public-links/{uuid4()}", headers=actors["other"]["headers"])
    assert hidden.json() == missing.json()


def test_reassignment_denies_replay_and_preserves_public_link(client, actors, context):
    request, ids = context
    key = uuid4()
    selection = publish(client, actors, request, ids, key=key).json()
    link = issue(client, actors, selection).json()
    assert (
        write(
            client,
            actors,
            "PATCH",
            f"/api/requests/{request['id']}/assignee",
            {"version": 3, "manager_id": str(actors["other"]["id"])},
            actor="head",
        ).status_code
        == 200
    )
    assert publish(client, actors, request, ids, key=key).status_code == 404
    assert issue(client, actors, selection).status_code == 404
    assert (
        client.get(
            f"/api/selections/{selection['id']}", headers=actors["other"]["headers"]
        ).status_code
        == 200
    )
    assert client.get(public_path(link)).status_code == 200


def test_selection_replay_after_restart_and_conflicting_payload(
    client, actors, context, settings, database
):
    request, ids = context
    key = uuid4()
    first = publish(client, actors, request, ids, key=key)
    with TestClient(create_app(settings)) as restarted:
        second = publish(restarted, actors, request, ids, key=key)
    assert first.status_code == second.status_code == 201 and first.json() == second.json()
    conflict = publish(client, actors, request, list(reversed(ids)), key=key)
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Selection)) == 1
        assert session.get(TravelRequest, UUID(request["id"])).version == 3


def test_foreign_item_and_database_relationships(client, actors, context, database):
    request, ids = context
    first = publish(client, actors, request, ids).json()
    second_request = create_request(client, actors, request["client_id"]).json()
    second_request = action(client, actors, second_request, "start-work").json()
    second = publish(client, actors, second_request, ids).json()
    result = write(
        client,
        actors,
        "PUT",
        f"/api/requests/{request['id']}/selected-tour",
        {"version": 3, "selection_item_id": second["items"][0]["id"]},
    )
    assert result.status_code == 404
    with pytest.raises(IntegrityError) as failure, database.sessions.begin() as session:
        session.get(TravelRequest, UUID(second_request["id"])).selected_selection_item_id = UUID(
            first["items"][0]["id"]
        )
        session.flush()
    assert failure.value.orig.diag.constraint_name == "fk_requests_selected_item_request"
    with pytest.raises(IntegrityError) as failure, database.sessions.begin() as session:
        source = session.get(SelectionItem, UUID(first["items"][0]["id"]))
        other_offer = session.scalar(
            select(TourOffer.id)
            .where(TourOffer.id.not_in([UUID(identity) for identity in ids]))
            .limit(1)
        )
        session.add(
            SelectionItem(
                selection_id=UUID(first["id"]),
                request_id=UUID(second_request["id"]),
                tour_offer_id=other_offer,
                position=99,
                offer_snapshot=source.offer_snapshot,
            )
        )
        session.flush()
    assert failure.value.orig.diag.constraint_name == "fk_selection_items_selection_request"


@pytest.mark.parametrize(
    "params", [{"sort": "price"}, {"page": 0}, {"page_size": 101}, {"unknown": "x"}]
)
def test_selection_pagination_validation(client, actors, context, params):
    result = client.get(
        f"/api/requests/{context[0]['id']}/selections",
        params=params,
        headers=actors["manager"]["headers"],
    )
    assert result.status_code == 422
    validate("Error", result.json())


def test_only_configured_origin_is_used(client, actors, context, settings):
    selection = publish(client, actors, *context).json()
    with TestClient(
        create_app(settings.model_copy(update={"public_app_url": "https://crm.example.test"}))
    ) as connection:
        response = connection.post(
            f"/api/selections/{selection['id']}/public-link",
            headers={
                **actors["manager"]["headers"],
                "Host": "attacker.example",
                "X-Forwarded-Host": "attacker.example",
            },
        )
    assert response.status_code == 201 and response.json()["url"].startswith(
        "https://crm.example.test/public/selections/"
    )


@pytest.mark.parametrize(
    "origin",
    [
        "ftp://example.com",
        "https://example.com/path",
        "https://user:private@example.com",
        "https://example.com/?token=private",
        "https://example.com/#private",
        "not-url",
        "http://example.com:999999",
    ],
)
def test_invalid_public_origin_is_rejected(settings, origin):
    values = settings.model_dump()
    values["public_app_url"] = origin
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    "mode", ["same_key", "different_keys", "issue_and_replace", "select_and_return", "two_issues"]
)
def test_concurrent_selection_commands(client, actors, context, settings, database, mode):
    request, ids = context
    original = (
        publish(client, actors, request, ids).json()
        if mode in ("issue_and_replace", "select_and_return", "two_issues")
        else None
    )
    if original:
        request = read_request(client, actors, request["id"])
    barrier = Barrier(2)
    key = uuid4()

    def run(index):
        with TestClient(create_app(settings)) as connection:
            barrier.wait(timeout=15)
            if mode == "two_issues" or (mode == "issue_and_replace" and index == 0):
                return issue(connection, actors, original)
            if mode == "select_and_return":
                if index == 0:
                    return write(
                        connection,
                        actors,
                        "PUT",
                        f"/api/requests/{request['id']}/selected-tour",
                        {"version": 3, "selection_item_id": original["items"][0]["id"]},
                    )
                return action(connection, actors, request, "return-to-work")
            return publish(
                connection, actors, request, ids, key=key if mode == "same_key" else uuid4()
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    if mode == "same_key":
        assert [r.status_code for r in results] == [201, 201] and results[0].json() == results[
            1
        ].json()
    elif mode == "issue_and_replace":
        assert results[1].status_code == 201 and results[0].status_code in (201, 409)
        if results[0].status_code == 201:
            assert client.get(public_path(results[0].json())).status_code == 404
    elif mode == "two_issues":
        assert [result.status_code for result in results] == [201, 201]
        assert sorted(client.get(public_path(result.json())).status_code for result in results) == [
            200,
            404,
        ]
    else:
        assert sorted(r.status_code for r in results) == (
            [200, 409] if mode == "select_and_return" else [201, 409]
        )
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Selection)) == (
            2 if mode == "issue_and_replace" else 1
        )


def test_public_privacy_redacts_uvicorn_path_and_error_path():
    secret = new_token()[0]

    async def receive():
        return {"type": "http.request", "body": b""}

    for fails in (False, True):
        scope = {
            "type": "http",
            "path": "/api/public/selections/" + secret,
            "raw_path": ("/api/public/selections/" + secret).encode(),
            "query_string": ("copy=" + secret).encode(),
            "path_params": {"token": secret},
        }
        messages = []

        async def app(scope, receive, send, *, fails=fails):
            assert scope["path"].endswith(secret)
            if fails:
                raise RuntimeError("test failure")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})

        async def send(message, *, scope=scope, messages=messages):
            assert secret not in get_path_with_query_string(scope)
            messages.append(message)

        middleware = PublicResponsePrivacy(app)
        if fails:
            with pytest.raises(RuntimeError):
                asyncio.run(middleware(scope, receive, send))
        else:
            asyncio.run(middleware(scope, receive, send))
            headers = dict(messages[0]["headers"])
            assert (
                headers[b"cache-control"] == b"no-store"
                and headers[b"referrer-policy"] == b"no-referrer"
            )
        assert secret not in str(scope)


def test_public_unexpected_error_keeps_privacy_headers(
    client, actors, context, settings, monkeypatch
):
    from app.modules.tours import selection_service

    def fail(_session, _token):
        raise RuntimeError("unexpected test failure")

    monkeypatch.setattr(selection_service, "public_selection", fail)
    with TestClient(create_app(settings), raise_server_exceptions=False) as connection:
        result = connection.get("/api/public/selections/" + new_token()[0])
    assert result.status_code == 500
    validate("Error", result.json())
    assert (
        result.headers["cache-control"] == "no-store"
        and result.headers["referrer-policy"] == "no-referrer"
    )


def test_token_generation_and_wrong_purpose_is_not_public_selection(
    client, actors, context, database
):
    generated = [new_token() for _ in range(30)]
    assert len({token for token, _ in generated}) == 30
    token, digest = generated[0]
    with database.sessions.begin() as session:
        now = datetime.now(UTC)
        session.add(
            PublicLink(
                purpose="tourists",
                request_id=UUID(context[0]["id"]),
                selection_id=None,
                token_hash=digest,
                created_by_id=actors["manager"]["id"],
                created_at=now,
                expires_at=now + timedelta(days=7),
            )
        )
    assert client.get("/api/public/selections/" + token).status_code == 404


def test_stale_commands_do_not_revoke_a_live_link(client, actors, context):
    request, ids = context
    selection = publish(client, actors, request, ids).json()
    link = issue(client, actors, selection).json()
    results = [
        publish(client, actors, request, ids),
        write(
            client,
            actors,
            "PUT",
            f"/api/requests/{request['id']}/selected-tour",
            {"version": 2, "selection_item_id": selection["items"][0]["id"]},
        ),
        action(client, actors, request, "return-to-work"),
    ]
    assert all(
        result.status_code == 409 and result.json()["code"] == "version_conflict"
        for result in results
    )
    assert client.get(public_path(link)).status_code == 200
    assert read_request(client, actors, request["id"])["version"] == 3


def test_selection_pages_and_public_projection_have_bounded_queries(
    client, actors, context, application
):
    request, ids = context
    for _ in range(3):
        selection = publish(client, actors, request, ids).json()
        request = read_request(client, actors, request["id"])
    link = issue(client, actors, selection).json()
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    engine = application.state.database.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = client.get(
            f"/api/requests/{request['id']}/selections", headers=actors["manager"]["headers"]
        )
        assert result.status_code == 200 and result.json()["total"] == 3 and len(statements) <= 7
        assert result.json()["items"][0]["id"] == selection["id"]
        statements.clear()
        assert client.get(public_path(link)).status_code == 200 and len(statements) <= 2
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    empty = client.get(
        f"/api/requests/{request['id']}/selections",
        params={"page": 99},
        headers=actors["manager"]["headers"],
    ).json()
    assert empty["total"] == 3 and empty["items"] == []


def test_public_link_database_constraints(client, actors, context, database):
    selection = publish(client, actors, *context).json()
    now = datetime.now(UTC)
    base = {
        "purpose": "selection",
        "request_id": None,
        "selection_id": UUID(selection["id"]),
        "token_hash": new_token()[1],
        "created_by_id": actors["manager"]["id"],
        "created_at": now,
        "expires_at": now + timedelta(days=7),
    }
    for changes in (
        {"purpose": "unknown"},
        {"selection_id": None},
        {"request_id": UUID(context[0]["id"])},
        {"token_hash": "raw-token"},
        {"expires_at": now},
    ):
        with pytest.raises(IntegrityError), database.sessions.begin() as session:
            session.add(PublicLink(**{**base, **changes}))
            session.flush()
    with database.sessions.begin() as session:
        session.add(PublicLink(**base))
    with pytest.raises(IntegrityError) as failure, database.sessions.begin() as session:
        session.add(PublicLink(**{**base, "token_hash": new_token()[1]}))
        session.flush()
    assert failure.value.orig.diag.constraint_name == "uq_public_links_live_selection"
