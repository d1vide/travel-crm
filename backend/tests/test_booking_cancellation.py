from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.audit import AuditRecord
from app.core.public_links import PublicLink
from app.main import create_app
from app.modules.bookings.completion import business_date
from app.modules.bookings.models import Booking
from app.modules.payments import service as payments
from app.modules.payments.models import Payment, PaymentNotification
from app.modules.requests.models import RequestStatus, TravelRequest
from tests.payment_gateway import gateway as gateway
from tests.test_bookings import card, command, create
from tests.test_bookings import context as context
from tests.test_clients import actors as actors
from tests.test_clients import validate
from tests.test_payments import create as pay
from tests.test_payments import read as read_payment
from tests.test_payments import ready as ready
from tests.test_requests import action, write
from tests.test_selections import publish, read_request


def ask(client, actors, booking, **kwargs):
    return command(
        client, actors, booking, "request-cancellation", reason="Просьба клиента", **kwargs
    )


def confirm(client, actors, booking, **kwargs):
    return command(
        client,
        actors,
        booking,
        "confirm-cancellation",
        supplier_response="Поставщик подтвердил",
        **kwargs,
    )


def test_unpaid_cancellation_reopens_request_and_preserves_snapshots(
    client, actors, ready, context, database
):
    request, original = ready
    before = read_request(client, actors, request["id"])
    asked = ask(client, actors, original)
    assert asked.status_code == 200
    pending = asked.json()
    validate("Booking", pending)
    assert pending["status"] == "cancellation_requested"
    assert pending["allowed_actions"] == ["confirm_cancellation", "reject_cancellation"]
    current = read_request(client, actors, request["id"])
    assert current["status"] == "booked" and current["version"] == before["version"] + 1
    assert current["active_booking"]["status"] == "cancellation_requested"
    assert not current["tourist_form_editable"] and "complete" not in current["allowed_actions"]
    cancelled = confirm(client, actors, pending)
    assert cancelled.status_code == 200
    result = cancelled.json()
    validate("Booking", result)
    assert result["status"] == "cancelled" and result["cancelled_at"]
    assert result["cancellation_reason"] == "Просьба клиента"
    assert result["cancellation_response"] == "Поставщик подтвердил"
    assert result["version"] == original["version"] + 2 and result["allowed_actions"] == []
    for field in ("offer_snapshot", "tourists", "confirmed_at", "supplier_booking_number"):
        assert result[field] == original[field]
    current = read_request(client, actors, request["id"])
    assert current["status"] == "in_progress" and current["version"] == before["version"] + 2
    assert current["active_booking"] is None and current["selected_offer"] is None
    assert current["cancelled_at"] is None and current["cancellation_reason"] is None
    assert current["tourist_form_editable"] and not current["tourist_link"]["is_active"]
    with database.sessions() as session:
        links = session.scalars(select(PublicLink)).all()
        assert links and all(link.revoked_at is not None for link in links)
        history = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "booking_cancelled")
        ).all()
        assert {record.entity_type for record in history} == {"request", "booking"}
    # A fresh selection/booking is a separate attempt, not reuse of the cancelled one.
    selection = publish(client, actors, current, [context[1]["items"][0]["tour_offer_id"]]).json()
    current = read_request(client, actors, request["id"])
    current = write(
        client,
        actors,
        "PUT",
        f"/api/requests/{request['id']}/selected-tour",
        {"version": current["version"], "selection_item_id": selection["items"][0]["id"]},
    ).json()
    next_booking = create(client, actors, current)
    assert next_booking.status_code == 201 and next_booking.json()["id"] != original["id"]
    assert card(client, actors, original["id"]).json() == result


@pytest.mark.parametrize(
    "outcome,full", [("succeeded", False), ("succeeded", True), ("failed", False)]
)
def test_cancel_with_payment_keeps_money_on_old_booking(
    client, actors, ready, gateway, outcome, full
):
    request, booking = ready
    payment = pay(client, actors, booking, booking["total_amount"] if full else "1000.00").json()
    gateway.outcome(payment, outcome)
    assert read_payment(client, actors, payment["id"]).json()["status"] == outcome
    booking = card(client, actors, booking["id"]).json()
    cancelled = confirm(client, actors, ask(client, actors, booking).json()).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["paid_amount"] == (payment["amount"] if outcome == "succeeded" else "0.00")
    assert (
        cancelled["available_payment_amount"] == "0.00" and cancelled["refunded_amount"] == "0.00"
    )
    current = read_request(client, actors, request["id"])
    assert current["status"] == ("cancelled" if outcome == "succeeded" else "in_progress")
    if outcome == "succeeded":
        assert current["cancelled_at"] == cancelled["cancelled_at"]
        assert current["cancellation_reason"] == "Просьба клиента"
        assert "resume" in current["allowed_actions"]
        resumed = action(client, actors, current, "resume").json()
        assert resumed["status"] == "in_progress" and resumed["cancelled_at"] is None
    assert read_payment(client, actors, payment["id"]).json()["status"] == outcome
    assert pay(client, actors, cancelled).json()["code"] == "invalid_transition"


def test_pending_payment_blocks_final_cancellation_until_verified(client, actors, ready, gateway):
    request, booking = ready
    payment = pay(client, actors, booking).json()
    gateway.outcome(payment, "timeout")
    booking = card(client, actors, booking["id"]).json()
    waiting = ask(client, actors, booking).json()
    assert waiting["allowed_actions"] == ["reject_cancellation"]
    assert confirm(client, actors, waiting).json()["code"] == "invalid_transition"
    assert pay(client, actors, waiting).json()["code"] == "invalid_transition"
    assert read_request(client, actors, request["id"])["status"] == "booked"
    gateway.outcome(payment, "succeeded")
    read_payment(client, actors, payment["id"])
    assert confirm(client, actors, waiting).json()["code"] == "version_conflict"
    updated = card(client, actors, booking["id"]).json()
    assert "confirm_cancellation" in updated["allowed_actions"]
    assert confirm(client, actors, updated).json()["status"] == "cancelled"


def test_supplier_rejection_restores_booking_and_new_request_clears_response(client, actors, ready):
    request, booking = ready
    asked = ask(client, actors, booking).json()
    rejected = command(
        client, actors, asked, "reject-cancellation", reason="Отказ поставщика"
    ).json()
    assert rejected["status"] == "confirmed" and rejected["cancelled_at"] is None
    assert rejected["cancellation_response"] == "Отказ поставщика"
    assert "create_payment" in rejected["allowed_actions"]
    assert read_request(client, actors, request["id"])["status"] == "booked"
    again = ask(client, actors, rejected).json()
    assert again["status"] == "cancellation_requested" and again["cancellation_response"] is None


@pytest.mark.parametrize(
    "name,fields",
    [
        ("request-cancellation", {"reason": "Просьба"}),
        ("confirm-cancellation", {"supplier_response": "Ответ"}),
        ("reject-cancellation", {"reason": "Отказ"}),
    ],
)
def test_cancellation_roles_replays_and_reassignment(client, actors, ready, name, fields):
    request, booking = ready
    if name != "request-cancellation":
        booking = ask(client, actors, booking).json()
    key = uuid4()
    for actor, expected in (("other", 404), ("accountant", 403)):
        assert command(client, actors, booking, name, actor=actor, **fields).status_code == expected
    result = command(client, actors, booking, name, key=key, **fields)
    assert result.status_code == 200
    assert command(client, actors, booking, name, key=key, **fields).json() == result.json()
    changed = {field: value + " другое" for field, value in fields.items()}
    assert (
        command(client, actors, booking, name, key=key, **changed).json()["code"]
        == "idempotency_conflict"
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
    assert command(client, actors, booking, name, key=key, **fields).status_code == 404
    assert card(client, actors, booking["id"], "head").status_code == 200


@pytest.mark.parametrize(
    "name,fields",
    [
        ("request-cancellation", {"reason": "  "}),
        ("request-cancellation", {"reason": None}),
        ("reject-cancellation", {"reason": 123}),
        ("confirm-cancellation", {"supplier_response": "\x00"}),
        ("confirm-cancellation", {"supplier_response": "  "}),
        ("confirm-cancellation", {"supplier_response": "Ответ", "status": "cancelled"}),
    ],
)
def test_cancellation_validates_supplier_and_reason(client, actors, ready, name, fields):
    booking = ready[1]
    assert command(client, actors, booking, name, **fields).status_code == 422


def test_pending_and_completed_bookings_cannot_be_cancelled(client, actors, context, database):
    request = context[0]
    pending = create(client, actors, request).json()
    assert ask(client, actors, pending).json()["code"] == "invalid_transition"
    confirmed = command(
        client, actors, pending, "confirm", supplier_booking_number="CANCEL-34"
    ).json()
    with database.sessions.begin() as session:
        row = session.get(TravelRequest, UUID(request["id"]))
        row.status = RequestStatus.COMPLETED
        row.completed_at = session.scalar(select(func.clock_timestamp()))
    assert (
        "request_cancellation"
        not in card(client, actors, confirmed["id"]).json()["allowed_actions"]
    )
    assert ask(client, actors, confirmed).json()["code"] == "invalid_transition"


@pytest.mark.parametrize("mode", ["same_key", "different_keys", "confirm_reject"])
def test_concurrent_cancellation_is_atomic(client, actors, ready, settings, database, mode):
    request, booking = ready
    if mode == "confirm_reject":
        booking = ask(client, actors, booking).json()
    barrier, key = Barrier(2), uuid4()

    def run(index):
        with TestClient(create_app(settings)) as connection:
            barrier.wait(timeout=20)
            if mode == "confirm_reject":
                return (
                    confirm(connection, actors, booking)
                    if index == 0
                    else command(connection, actors, booking, "reject-cancellation", reason="Отказ")
                )
            return ask(connection, actors, booking, key=key if mode == "same_key" else uuid4())

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, range(2)))
    assert sorted(response.status_code for response in results) == (
        [200, 200] if mode == "same_key" else [200, 409]
    )
    current = card(client, actors, booking["id"]).json()
    assert current["version"] == booking["version"] + 1
    with database.sessions() as session:
        assert session.scalar(
            select(func.count())
            .select_from(AuditRecord)
            .where(
                AuditRecord.entity_id == UUID(booking["id"]),
                AuditRecord.action.in_(
                    (
                        "booking_cancellation_requested",
                        "booking_cancellation_rejected",
                        "booking_cancelled",
                    )
                ),
            )
        ) == (2 if mode == "confirm_reject" else 1)
    assert read_request(client, actors, request["id"])["status"] in ("booked", "in_progress")


def test_payment_result_racing_cancellation_cannot_be_lost(
    client, actors, ready, gateway, database, settings
):
    request, booking = ready
    payment = pay(client, actors, booking).json()
    waiting = ask(client, actors, card(client, actors, booking["id"]).json()).json()
    gateway.outcome(payment, "succeeded")
    barrier = Barrier(2)

    def run(index):
        barrier.wait(timeout=20)
        if index == 0:
            with database.sessions() as session:
                payments.synchronize_system(session, UUID(payment["id"]), gateway.adapter)
            return None
        with TestClient(create_app(settings)) as connection:
            return confirm(connection, actors, waiting)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, range(2)))
    assert results[1].status_code == 409
    booking = card(client, actors, booking["id"]).json()
    assert (
        booking["status"] == "cancellation_requested"
        and booking["paid_amount"] == payment["amount"]
    )
    assert confirm(client, actors, booking).status_code == 200
    assert read_request(client, actors, request["id"])["status"] == "cancelled"
    with database.sessions() as session:
        assert session.get(Payment, UUID(payment["id"])).status == "succeeded"
        assert session.scalar(select(func.count()).select_from(PaymentNotification)) == 2


def test_resume_checks_pending_across_previous_attempts(client, actors, ready, database):
    request, booking = ready
    with database.sessions.begin() as session:
        old = session.get(Booking, UUID(booking["id"]))
        old.status = "cancelled"
        old.cancelled_at = session.scalar(select(func.clock_timestamp()))
        row = session.get(TravelRequest, UUID(request["id"]))
        row.status = RequestStatus.CANCELLED
        row.selected_selection_item_id = None
        session.add(Payment(booking_id=old.id, amount=1000, currency="RUB"))
    current = read_request(client, actors, request["id"])
    assert "resume" not in current["allowed_actions"]
    assert action(client, actors, current, "resume").json()["code"] == "invalid_transition"


def test_payment_creation_racing_cancellation_obeys_booking_version(
    client, actors, ready, gateway, database
):
    _request, booking = ready
    barrier = Barrier(2)

    def run(index):
        with TestClient(create_app(gateway.crm_settings)) as connection:
            barrier.wait(timeout=20)
            return (
                ask(connection, actors, booking) if index == 0 else pay(connection, actors, booking)
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, range(2)))
    assert sorted(response.status_code for response in results) in ([200, 409], [202, 409])
    current = card(client, actors, booking["id"]).json()
    with database.sessions() as session:
        count = session.scalar(select(func.count()).select_from(Payment))
    if current["status"] == "cancellation_requested":
        assert count == 0 and current["reserved_payment_amount"] == "0.00"
    else:
        assert count == 1 and current["reserved_payment_amount"] == "1000.00"
        assert ask(client, actors, current).json()["allowed_actions"] == ["reject_cancellation"]


def test_completion_racing_cancellation_leaves_one_valid_state(
    client, actors, ready, gateway, database, settings
):
    request, booking = ready
    payment = pay(client, actors, booking, booking["total_amount"]).json()
    gateway.outcome(payment, "succeeded")
    read_payment(client, actors, payment["id"])
    with database.sessions.begin() as session:
        row = session.get(Booking, UUID(booking["id"]))
        today = business_date(session)
        row.offer_snapshot = {
            **row.offer_snapshot,
            "starts_on": str(today - timedelta(days=8)),
            "ends_on": str(today - timedelta(days=1)),
        }
    booking = card(client, actors, booking["id"]).json()
    request = read_request(client, actors, request["id"])
    barrier = Barrier(2)

    def run(index):
        with TestClient(create_app(settings)) as connection:
            barrier.wait(timeout=20)
            return (
                ask(connection, actors, booking)
                if index == 0
                else action(connection, actors, request, "complete")
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, range(2)))
    assert sorted(response.status_code for response in results) == [200, 409]
    current_request = read_request(client, actors, request["id"])
    current_booking = card(client, actors, booking["id"]).json()
    assert (current_request["status"], current_booking["status"]) in (
        ("completed", "confirmed"),
        ("booked", "cancellation_requested"),
    )


def test_cancellation_requires_authentication_key_and_existing_booking(client, actors, ready):
    booking = ready[1]
    url = f"/api/bookings/{booking['id']}/actions/request-cancellation"
    payload = {"version": booking["version"], "reason": "Просьба"}
    assert client.post(url, json=payload).status_code == 401
    assert client.post(url, json=payload, headers=actors["manager"]["headers"]).status_code == 422
    assert ask(client, actors, {**booking, "id": str(uuid4())}).status_code == 404
