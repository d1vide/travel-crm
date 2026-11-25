from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from app.core.audit import AuditRecord
from app.core.idempotency import IdempotencyRecord
from app.main import create_app
from app.modules.bookings.models import Booking, BookingTourist
from app.modules.requests.models import RequestStatus, TravelRequest
from app.modules.tourists.models import Tourist
from app.modules.tours.models import TourOffer
from tests.test_clients import actors as actors
from tests.test_clients import create as create_client
from tests.test_clients import validate
from tests.test_requests import action, write
from tests.test_requests import create as create_request
from tests.test_selections import publish, read_request
from tests.test_tourists import body, issue, path, staff_list, staff_submit, submit


@pytest.fixture
def context(client, actors, database):
    client_id = create_client(client, actors).json()["id"]
    request = create_request(client, actors, client_id).json()
    request = action(client, actors, request, "start-work").json()
    with database.sessions() as session:
        offer_id = str(
            session.scalar(
                select(TourOffer.id)
                .where(TourOffer.tourist_count == 2)
                .order_by(TourOffer.id)
                .limit(1)
            )
        )
    selection = publish(client, actors, request, [offer_id]).json()
    request = read_request(client, actors, request["id"])
    chosen = write(
        client,
        actors,
        "PUT",
        f"/api/requests/{request['id']}/selected-tour",
        {"version": request["version"], "selection_item_id": selection["items"][0]["id"]},
    )
    assert chosen.status_code == 200
    request = chosen.json()
    assert staff_submit(client, actors, request, body(request)).status_code == 200
    request = read_request(client, actors, request["id"])
    link = issue(client, actors, request).json()
    return request, selection, link


def create(client, actors, request, *, key=None, actor="manager", **changes):
    return write(
        client,
        actors,
        "POST",
        f"/api/requests/{request['id']}/bookings",
        {"version": request["version"], **changes},
        actor,
        key,
    )


def command(client, actors, booking, name, *, key=None, actor="manager", **changes):
    return write(
        client,
        actors,
        "POST",
        f"/api/bookings/{booking['id']}/actions/{name}",
        {"version": booking["version"], **changes},
        actor,
        key,
    )


def card(client, actors, identity, actor="manager"):
    return client.get(f"/api/bookings/{identity}", headers=actors[actor]["headers"])


def test_create_confirm_contract_and_frozen_snapshots(client, actors, context, database):
    request, selection, link = context
    assert "create_booking" in request["allowed_actions"]
    response = create(client, actors, request)
    assert response.status_code == 201, response.text
    assert response.headers["Cache-Control"] == "no-store"
    booking = response.json()
    validate("Booking", booking)
    assert booking["status"] == "pending_confirmation" and booking["version"] == 1
    assert booking["offer_snapshot"] == selection["items"][0]["offer_snapshot"]
    assert (
        booking["total_amount"] == booking["remaining_amount"] == booking["offer_snapshot"]["price"]
    )
    assert (
        booking["paid_amount"]
        == booking["reserved_payment_amount"]
        == booking["refunded_amount"]
        == booking["available_payment_amount"]
        == "0.00"
    )
    assert booking["tourists"] == [] and booking["allowed_actions"] == ["confirm", "reject"]
    current = read_request(client, actors, request["id"])
    assert current["version"] == request["version"] + 1 and current["status"] == "offer_prepared"
    assert current["active_booking"]["id"] == booking["id"]
    assert not current["tourist_form_editable"] and current["allowed_actions"] == []
    form = client.get(path(link)).json()
    assert not form["is_editable"] and form["closed_reason"]
    original_tourists = staff_list(client, actors, request).json()
    response = command(
        client, actors, booking, "confirm", supplier_booking_number="  DEMO-BOOK-14  "
    )
    assert response.status_code == 200, response.text
    confirmed = response.json()
    validate("Booking", confirmed)
    assert confirmed["status"] == "confirmed" and confirmed["version"] == 2
    assert confirmed["supplier_booking_number"] == "DEMO-BOOK-14" and confirmed[
        "confirmed_at"
    ].endswith("Z")
    assert confirmed["allowed_actions"] == ["request_cancellation", "create_payment"]
    assert confirmed["available_payment_amount"] == confirmed["total_amount"]
    assert [tourist["tourist_id"] for tourist in confirmed["tourists"]] == [
        tourist["id"] for tourist in original_tourists
    ]
    assert (
        confirmed["tourists"][0]["tourist_snapshot"]["document_number"]
        == original_tourists[0]["document_number"]
    )
    current = read_request(client, actors, request["id"])
    assert current["status"] == "booked" and current["version"] == request["version"] + 2
    assert current["active_booking"]["status"] == "confirmed"
    with database.sessions.begin() as session:
        session.get(TourOffer, UUID(selection["items"][0]["tour_offer_id"])).price = Decimal(
            "999.99"
        )
        session.get(
            Tourist, UUID(original_tourists[0]["id"])
        ).document_number = "FICTIONAL-LATER-CHANGE"
    assert card(client, actors, booking["id"]).json() == confirmed
    history = client.get(
        f"/api/requests/{request['id']}/history", headers=actors["manager"]["headers"]
    )
    validate("AuditRecordPage", history.json())
    assert "FICTIONAL" not in history.text and "DEMO-BOOK" not in history.text
    assert len([row for row in history.json()["items"] if row["entity_type"] == "booking"]) == 2


def test_reject_and_explicit_new_choice_allow_another_attempt(client, actors, context):
    request, selection, link = context
    booking = create(client, actors, request).json()
    response = command(client, actors, booking, "reject", reason="  Учебный отказ поставщика  ")
    assert response.status_code == 200
    rejected = response.json()
    validate("Booking", rejected)
    assert (
        rejected["status"] == "rejected"
        and rejected["rejection_reason"] == "Учебный отказ поставщика"
    )
    assert rejected["tourists"] == [] and rejected["allowed_actions"] == []
    current = read_request(client, actors, request["id"])
    assert current["active_booking"] is None and current["selected_offer"] is None
    assert current["status"] == "offer_prepared" and current["tourist_form_editable"]
    assert "create_booking" not in current["allowed_actions"]
    assert create(client, actors, current).status_code == 409
    current = write(
        client,
        actors,
        "PUT",
        f"/api/requests/{request['id']}/selected-tour",
        {"version": current["version"], "selection_item_id": selection["items"][0]["id"]},
    ).json()
    second = create(client, actors, current)
    assert second.status_code == 201 and second.json()["id"] != booking["id"]
    page = client.get(
        f"/api/requests/{request['id']}/bookings", headers=actors["manager"]["headers"]
    ).json()
    validate("BookingPage", page)
    assert page["total"] == 2 and [row["id"] for row in page["items"]] == [
        second.json()["id"],
        booking["id"],
    ]
    assert card(client, actors, booking["id"]).json() == rejected


def test_pending_booking_blocks_all_related_commands(client, actors, context):
    request, selection, link = context
    booking = create(client, actors, request).json()
    current = read_request(client, actors, request["id"])
    for name, fields in (("cancel", {"reason": "Учебная отмена"}), ("return-to-work", {})):
        assert action(client, actors, current, name, **fields).status_code == 409
    assert (
        publish(client, actors, current, [selection["items"][0]["tour_offer_id"]]).status_code
        == 409
    )
    assert (
        write(
            client,
            actors,
            "PUT",
            f"/api/requests/{request['id']}/selected-tour",
            {"version": current["version"], "selection_item_id": selection["items"][0]["id"]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/selections/{selection['id']}/public-link", headers=actors["manager"]["headers"]
        ).status_code
        == 409
    )
    assert issue(client, actors, current).json()["code"] == "tourist_form_closed"
    assert (
        staff_submit(client, actors, current, body(current)).json()["code"] == "tourist_form_closed"
    )
    assert submit(client, link, body(current)).json()["code"] == "tourist_form_closed"
    assert create(client, actors, current).status_code == 409
    assert card(client, actors, booking["id"]).json() == booking


@pytest.mark.parametrize("defect", ["missing", "count", "tour_count", "not_selected"])
def test_creation_validates_children_atomically(client, actors, context, database, defect):
    request, _selection, _link = context
    with database.sessions.begin() as session:
        row = session.get(TravelRequest, UUID(request["id"]))
        if defect == "missing":
            session.scalar(
                select(Tourist).where(Tourist.request_id == row.id).limit(1)
            ).removed_at = datetime.now(UTC)
        elif defect == "count":
            row.tourist_count = 3
        elif defect == "tour_count":
            row.tourist_count = 1
            session.scalar(
                select(Tourist).where(Tourist.request_id == row.id).limit(1)
            ).removed_at = datetime.now(UTC)
        else:
            row.selected_selection_item_id = None
    response = create(client, actors, request)
    assert response.status_code == 409
    assert "FICTIONAL" not in response.text
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Booking)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(IdempotencyRecord.resource_type == "booking")
            )
            == 0
        )
    assert read_request(client, actors, request["id"])["version"] == request["version"]


@pytest.mark.parametrize(
    "status",
    [
        RequestStatus.NEW,
        RequestStatus.IN_PROGRESS,
        RequestStatus.BOOKED,
        RequestStatus.CANCELLED,
        RequestStatus.COMPLETED,
    ],
)
def test_create_requires_offer_prepared(client, actors, context, database, status):
    request, _selection, _link = context
    with database.sessions.begin() as session:
        session.get(TravelRequest, UUID(request["id"])).status = status
    assert create(client, actors, request).status_code == 409


@pytest.mark.parametrize(
    "name,fields",
    [
        ("confirm", {}),
        ("confirm", {"supplier_booking_number": "  "}),
        ("confirm", {"supplier_booking_number": 12}),
        ("confirm", {"supplier_booking_number": "bad\x00value"}),
        ("reject", {}),
        ("reject", {"reason": "  "}),
    ],
)
def test_invalid_supplier_response_is_atomic(client, actors, context, name, fields):
    request, _selection, _link = context
    booking = create(client, actors, request).json()
    response = command(client, actors, booking, name, **fields)
    assert response.status_code == 422
    validate("Error", response.json())
    assert card(client, actors, booking["id"]).json() == booking


def test_create_and_action_replay_survive_restart(client, actors, context, settings, database):
    request, _selection, _link = context
    key = uuid4()
    created = create(client, actors, request, key=key)
    booking = created.json()
    confirm_key = uuid4()
    response = command(
        client,
        actors,
        booking,
        "confirm",
        key=confirm_key,
        supplier_booking_number="DEMO-14-REPEAT",
    )
    assert response.status_code == 200
    confirmed = response.json()
    with TestClient(create_app(settings)) as connection:
        assert create(connection, actors, request, key=key).json() == confirmed
        assert (
            command(
                connection,
                actors,
                booking,
                "confirm",
                key=confirm_key,
                supplier_booking_number="DEMO-14-REPEAT",
            ).json()
            == confirmed
        )
    assert (
        create(client, actors, request, key=key, version=request["version"] + 1).json()["code"]
        == "idempotency_conflict"
    )
    assert (
        command(
            client, actors, booking, "confirm", key=confirm_key, supplier_booking_number="OTHER-14"
        ).json()["code"]
        == "idempotency_conflict"
    )
    assert (
        command(client, actors, booking, "reject", reason="Учебный отказ").json()["code"]
        == "version_conflict"
    )
    assert (
        command(client, actors, confirmed, "reject", reason="Учебный отказ").json()["code"]
        == "invalid_transition"
    )
    with database.sessions() as session:
        records = session.scalars(
            select(IdempotencyRecord).where(IdempotencyRecord.resource_type == "booking")
        ).all()
        assert len(records) == 2
        assert all(row.result_metadata is None for row in records)


def test_roles_and_reassignment_recheck_read_and_replay(client, actors, context):
    request, _selection, _link = context
    key = uuid4()
    booking = create(client, actors, request, key=key).json()
    for actor, expected in (("other", 404), ("accountant", 403)):
        assert card(client, actors, booking["id"], actor).status_code == expected
        assert create(client, actors, request, actor=actor).status_code == expected
        assert (
            command(
                client, actors, booking, "confirm", actor=actor, supplier_booking_number="DEMO-14"
            ).status_code
            == expected
        )
        assert (
            client.get(
                f"/api/requests/{request['id']}/bookings", headers=actors[actor]["headers"]
            ).status_code
            == expected
        )
    assert client.get(f"/api/bookings/{booking['id']}").status_code == 401
    assert (
        card(client, actors, booking["id"], "other").json() == card(client, actors, uuid4()).json()
    )
    current = read_request(client, actors, request["id"])
    moved = write(
        client,
        actors,
        "PATCH",
        f"/api/requests/{request['id']}/assignee",
        {"version": current["version"], "manager_id": str(actors["other"]["id"])},
        "head",
    )
    assert moved.status_code == 200
    assert create(client, actors, request, key=key).status_code == 404
    assert card(client, actors, booking["id"]).status_code == 404
    assert (
        command(
            client, actors, booking, "confirm", actor="other", supplier_booking_number="DEMO-14"
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "mode", ["same_key", "different_keys", "confirm_reject", "book_edit", "book_replace"]
)
def test_concurrent_commands_keep_one_active_booking(
    client, actors, context, database, settings, mode
):
    request, selection, link = context
    booking = create(client, actors, request).json() if mode == "confirm_reject" else None
    barrier, key = Barrier(2), uuid4()

    def run(index):
        with TestClient(create_app(settings)) as connection:
            barrier.wait(timeout=20)
            if mode == "confirm_reject":
                return (
                    command(
                        connection, actors, booking, "confirm", supplier_booking_number="DEMO-14"
                    )
                    if index == 0
                    else command(connection, actors, booking, "reject", reason="Учебный отказ")
                )
            if mode == "book_edit" and index == 1:
                return submit(connection, link, body(request))
            if mode == "book_replace" and index == 1:
                return publish(
                    connection, actors, request, [selection["items"][0]["tour_offer_id"]]
                )
            return create(connection, actors, request, key=key if mode == "same_key" else uuid4())

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(run, range(2)))
    if mode == "same_key":
        assert [response.status_code for response in responses] == [201, 201]
        assert responses[0].json()["id"] == responses[1].json()["id"]
    elif mode == "confirm_reject":
        assert sorted(response.status_code for response in responses) == [200, 409]
    elif mode == "different_keys":
        assert sorted(response.status_code for response in responses) == [201, 409]
    else:
        assert len([response for response in responses if response.status_code < 300]) == 1
        assert len([response for response in responses if response.status_code == 409]) == 1
    with database.sessions() as session:
        rows = session.scalars(select(Booking)).all()
        assert len(rows) <= 1
        if mode == "book_edit" and responses[0].status_code == 201:
            assert client.get(path(link)).json()["is_editable"] is False


@pytest.mark.parametrize(
    "params", [{"page": 0}, {"page_size": 101}, {"sort": "created_at"}, {"unknown": "value"}]
)
def test_pagination_validation(client, actors, context, params):
    request, _selection, _link = context
    response = client.get(
        f"/api/requests/{request['id']}/bookings",
        params=params,
        headers=actors["manager"]["headers"],
    )
    assert response.status_code == 422


def test_database_unique_amount_and_cross_request_constraints(client, actors, context, database):
    request, _selection, _link = context
    booking = create(client, actors, request).json()
    values = {
        "request_id": UUID(request["id"]),
        "selection_item_id": UUID(booking["selection_item_id"]),
        "offer_snapshot": booking["offer_snapshot"],
        "total_amount": Decimal(booking["total_amount"]),
    }
    with pytest.raises(IntegrityError) as error, database.sessions.begin() as session:
        session.add(Booking(**values))
        session.flush()
    assert error.value.orig.diag.constraint_name == "uq_bookings_active_request"
    for changes in (
        {"total_amount": Decimal("-1.00")},
        {"total_amount": Decimal(booking["total_amount"]) + 1},
        {"request_id": uuid4()},
        {"currency": "USD"},
        {"status": "invalid"},
    ):
        with pytest.raises(IntegrityError), database.sessions.begin() as session:
            session.add(Booking(**{**values, **changes}))
            session.flush()
    with pytest.raises(IntegrityError), database.sessions.begin() as session:
        session.add(
            BookingTourist(
                booking_id=UUID(booking["id"]),
                request_id=UUID(request["id"]),
                tourist_id=uuid4(),
                position=0,
                tourist_snapshot={},
            )
        )
        session.flush()


def test_booking_pages_and_request_summary_use_bounded_queries(
    client, actors, context, application
):
    request, _selection, _link = context
    booking = create(client, actors, request).json()
    statements = []

    def capture(_connection, _cursor, statement, *_args):
        statements.append(statement)

    engine = application.state.database.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        page = client.get(
            f"/api/requests/{request['id']}/bookings", headers=actors["manager"]["headers"]
        )
        assert page.status_code == 200 and len(statements) <= 5
        assert page.json()["items"] == [booking]
        statements.clear()
        requests = client.get("/api/requests", headers=actors["manager"]["headers"])
        assert requests.status_code == 200 and len(statements) <= 11
        assert requests.json()["items"][0]["active_booking"]["id"] == booking["id"]
        assert "FICTIONAL" not in requests.text
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_successful_tourist_submission_can_be_replayed_while_booking_is_pending(
    client, actors, context
):
    request, _selection, link = context
    key, payload = uuid4(), body(request)
    first = submit(client, link, payload, key)
    assert first.status_code == 200
    current = read_request(client, actors, request["id"])
    assert create(client, actors, current).status_code == 201
    assert submit(client, link, payload, key).json() == first.json()
    assert submit(client, link, payload).json()["code"] == "tourist_form_closed"


def test_confirmation_rechecks_roster_without_partial_snapshots(client, actors, context, database):
    request, _selection, _link = context
    booking = create(client, actors, request).json()
    with database.sessions.begin() as session:
        session.scalar(
            select(Tourist).where(Tourist.request_id == UUID(request["id"])).limit(1)
        ).removed_at = datetime.now(UTC)
    result = command(client, actors, booking, "confirm", supplier_booking_number="DEMO-14")
    assert result.status_code == 409
    assert card(client, actors, booking["id"]).json() == booking
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BookingTourist)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditRecord)
                .where(AuditRecord.entity_type == "booking")
            )
            == 1
        )


def test_existing_foreign_ids_cannot_cross_booking_request_boundaries(
    client, actors, context, database
):
    request, selection, _link = context
    booking = create(client, actors, request).json()
    other = create_request(client, actors, request["client_id"]).json()
    other = action(client, actors, other, "start-work").json()
    assert staff_submit(client, actors, other, body(other)).status_code == 200
    other_tourist = staff_list(client, actors, other).json()[0]
    with pytest.raises(IntegrityError) as failure, database.sessions.begin() as session:
        session.add(
            Booking(
                request_id=UUID(other["id"]),
                selection_item_id=UUID(booking["selection_item_id"]),
                offer_snapshot=booking["offer_snapshot"],
                total_amount=Decimal(booking["total_amount"]),
            )
        )
        session.flush()
    assert failure.value.orig.diag.constraint_name == "fk_bookings_item_request"
    with pytest.raises(IntegrityError) as failure, database.sessions.begin() as session:
        session.add(
            BookingTourist(
                booking_id=UUID(booking["id"]),
                request_id=UUID(request["id"]),
                tourist_id=UUID(other_tourist["id"]),
                position=0,
                tourist_snapshot={},
            )
        )
        session.flush()
    assert failure.value.orig.diag.constraint_name == "fk_booking_tourists_tourist_request"


def test_catalogue_change_before_creation_does_not_change_agreed_price(
    client, actors, context, database
):
    request, selection, _link = context
    with database.sessions.begin() as session:
        row = session.get(TourOffer, UUID(selection["items"][0]["tour_offer_id"]))
        row.price = Decimal("1.00")
        row.is_active = False
    result = create(client, actors, request)
    assert result.status_code == 201
    assert result.json()["offer_snapshot"] == selection["items"][0]["offer_snapshot"]
    assert result.json()["total_amount"] == selection["items"][0]["offer_snapshot"]["price"]
