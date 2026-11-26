from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from stubs.delivery import Delivery
from stubs.main import create_app as create_stub
from stubs.protocol import dto
from stubs.store import Operation

from app.core.audit import AuditRecord
from app.main import create_app
from app.modules.bookings.completion import business_date
from app.modules.bookings.models import Booking
from app.modules.payments.models import Payment, PaymentNotification
from app.modules.payments.reconciliation import Reconciler
from tests.live_http import eventually, serve
from tests.payment_gateway import gateway as gateway
from tests.test_bookings import card as booking_card
from tests.test_bookings import context as context
from tests.test_clients import actors as actors
from tests.test_clients import validate
from tests.test_payments import create, read
from tests.test_payments import ready as ready
from tests.test_requests import action, write
from tests.test_selections import read_request


@pytest.fixture
def paid(client, actors, ready, gateway):
    request, booking = ready
    payment = create(client, actors, booking, booking["total_amount"]).json()
    assert gateway.outcome(payment, "succeeded").status_code == 200
    assert read(client, actors, payment["id"]).json()["status"] == "succeeded"
    return request, booking, payment


def notices(client, actors, actor="manager", **params):
    return client.get("/api/notifications", params=params, headers=actors[actor]["headers"])


def mark(client, actors, identity, actor="manager"):
    return client.post(f"/api/notifications/{identity}/read", headers=actors[actor]["headers"])


def test_notifications_are_own_and_read_is_idempotent(client, actors, paid):
    request, _booking, _payment = paid
    manager = notices(client, actors)
    assert manager.status_code == 200
    validate("NotificationPage", manager.json())
    notification = manager.json()["items"][0]
    assert manager.json()["total"] == manager.json()["unread_count"] == 1
    assert (
        notification["recipient_id"] == str(actors["manager"]["id"])
        and notification["request_id"] == request["id"]
    )
    assert notification["can_open_request"] and notification["read_at"] is None
    assert len(notices(client, actors, "head").json()["items"]) == 1
    assert notices(client, actors, "other").json()["total"] == 0
    assert notices(client, actors, "accountant").status_code == 403
    assert (
        mark(client, actors, notification["id"], "head").json()
        == mark(client, actors, uuid4()).json()
    )
    first = mark(client, actors, notification["id"])
    assert first.status_code == 200 and first.json()["read_at"].endswith("Z")
    validate("Notification", first.json())
    assert mark(client, actors, notification["id"]).json() == first.json()
    assert notices(client, actors, unread_only=True).json()["total"] == 0
    assert notices(client, actors).json()["unread_count"] == 0


def test_notification_links_disappear_after_reassignment(client, actors, paid):
    request, _booking, _payment = paid
    before = notices(client, actors).json()["items"][0]
    current = read_request(client, actors, request["id"])
    assert (
        write(
            client,
            actors,
            "PATCH",
            f"/api/requests/{request['id']}/assignee",
            {"version": current["version"], "manager_id": str(actors["other"]["id"])},
            "head",
        ).status_code
        == 200
    )
    after = notices(client, actors).json()["items"][0]
    assert (
        after["id"] == before["id"]
        and after["request_id"] is None
        and not after["can_open_request"]
    )
    assert notices(client, actors, "head").json()["items"][0]["can_open_request"]
    assert mark(client, actors, after["id"]).status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page_size": 101},
        {"sort": "created_at"},
        {"unread_only": "invalid"},
        {"recipient_id": str(uuid4())},
    ],
)
def test_notification_query_validation(client, actors, params):
    assert notices(client, actors, **params).status_code == 422


def test_notification_count_is_independent_of_page(client, actors, ready, gateway):
    request, booking = ready
    for _ in range(2):
        booking = booking_card(client, actors, booking["id"]).json()
        payment = create(client, actors, booking).json()
        assert gateway.outcome(payment, "succeeded").status_code == 200
        assert read(client, actors, payment["id"]).json()["status"] == "succeeded"
    page = notices(client, actors, page_size=1).json()
    assert len(page["items"]) == 1 and page["total"] == page["unread_count"] == 2
    assert mark(client, actors, page["items"][0]["id"]).status_code == 200
    empty = notices(client, actors, page=99, page_size=1, unread_only=True).json()
    assert empty["items"] == [] and empty["total"] == empty["unread_count"] == 1


def test_financial_bookings_do_not_expose_documents(client, actors, paid):
    request, booking, payment = paid
    for actor in ("head", "accountant"):
        response = client.get(
            "/api/financial-bookings",
            params={"request_id": request["id"], "status": "confirmed"},
            headers=actors[actor]["headers"],
        )
        assert response.status_code == 200
        validate("FinancialBookingPage", response.json())
        row = response.json()["items"][0]
        assert (
            row["paid_amount"] == booking["total_amount"]
            and row["remaining_amount"] == row["reserved_payment_amount"] == "0.00"
        )
        assert row["can_open_request"] == (actor == "head")
        assert (
            "document" not in response.text
            and "supplier_booking_number" not in response.text
            and "tourists" not in response.text
        )
    assert (
        client.get("/api/financial-bookings", headers=actors["manager"]["headers"]).status_code
        == 403
    )
    assert (
        client.get(
            "/api/financial-bookings",
            params={"request_id": str(uuid4())},
            headers=actors["head"]["headers"],
        ).status_code
        == 404
    )


def past_trip(database, booking, offset=-1):
    with database.sessions.begin() as session:
        today = business_date(session)
        row = session.get(Booking, UUID(booking["id"]))
        row.offer_snapshot = {
            **row.offer_snapshot,
            "starts_on": (today - timedelta(days=7)).isoformat(),
            "ends_on": (today + timedelta(days=offset)).isoformat(),
        }


def test_complete_requires_paid_finished_trip_and_replays(client, actors, paid, database):
    request, booking, _payment = paid
    current = read_request(client, actors, request["id"])
    assert "complete" not in current["allowed_actions"]
    assert action(client, actors, current, "complete").status_code == 409
    past_trip(database, booking)
    current = read_request(client, actors, request["id"])
    assert "complete" in current["allowed_actions"]
    key = uuid4()
    result = action(client, actors, current, "complete", key=key)
    assert result.status_code == 200
    validate("Request", result.json())
    assert result.json()["status"] == "completed" and result.json()["completed_at"].endswith("Z")
    assert result.json()["version"] == current["version"] + 1
    assert "complete" not in result.json()["allowed_actions"]
    assert action(client, actors, current, "complete", key=key).json() == result.json()
    assert action(client, actors, result.json(), "complete").status_code == 409
    assert (
        action(client, actors, result.json(), "cancel", reason="Учебная отмена").status_code == 409
    )


@pytest.mark.parametrize("offset", [0, 1])
def test_complete_waits_until_day_after_tour_ends(client, actors, paid, database, offset):
    request, booking, _payment = paid
    past_trip(database, booking, offset)
    current = read_request(client, actors, request["id"])
    assert "complete" not in current["allowed_actions"]
    assert action(client, actors, current, "complete").status_code == 409


def test_complete_rejects_unpaid_and_pending_balances(client, actors, ready, gateway, database):
    request, booking = ready
    past_trip(database, booking)
    current = read_request(client, actors, request["id"])
    assert action(client, actors, current, "complete").status_code == 409
    payment = create(client, actors, booking, booking["total_amount"]).json()
    current = read_request(client, actors, request["id"])
    assert action(client, actors, current, "complete").status_code == 409
    assert gateway.outcome(payment, "failed").status_code == 200
    assert read(client, actors, payment["id"]).json()["status"] == "failed"
    assert action(client, actors, current, "complete").status_code == 409


def test_complete_and_read_concurrency_are_idempotent(client, actors, paid, database, gateway):
    request, booking, _payment = paid
    past_trip(database, booking)
    current = read_request(client, actors, request["id"])
    barrier, key = Barrier(2), uuid4()

    def run(_index):
        with TestClient(create_app(gateway.crm_settings)) as connection:
            barrier.wait(timeout=15)
            return action(connection, actors, current, "complete", key=key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert [result.status_code for result in results] == [200, 200]
    assert results[0].json() == results[1].json()
    with database.sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditRecord)
                .where(AuditRecord.action == "completed")
            )
            == 1
        )


def test_authenticated_events_are_idempotent_and_reject_invalid_facts(
    client, actors, ready, gateway, database
):
    _request, booking = ready
    payment = create(client, actors, booking).json()
    assert gateway.outcome(payment, "succeeded").status_code == 200
    with gateway.sessions() as session:
        payload = dto(
            gateway.stub_settings, session.get(Operation, UUID(payment["external_operation_id"]))
        )
    header = {
        "Authorization": "Bearer " + gateway.stub_settings.payment_stub_key.get_secret_value()
    }
    assert client.post("/internal/payment-events", json=payload).status_code == 401
    assert (
        client.post(
            "/internal/payment-events", json=payload, headers=actors["manager"]["headers"]
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/internal/payment-events", json={**payload, "amount": "1.00"}, headers=header
        ).status_code
        == 409
    )
    for _ in range(2):
        assert (
            client.post("/internal/payment-events", json=payload, headers=header).status_code == 204
        )
    with database.sessions() as session:
        assert session.get(Payment, UUID(payment["id"])).status == "succeeded"
        assert session.scalar(select(func.count()).select_from(PaymentNotification)) == 2


def test_sender_retries_and_repeats_without_double_accounting(
    client, actors, ready, gateway, database
):
    _request, booking = ready
    payment = create(client, actors, booking).json()
    assert gateway.outcome(payment, "succeeded").status_code == 200
    with serve(create_app(gateway.crm_settings)) as url:
        settings = gateway.stub_settings.model_copy(
            update={
                "payment_callback_url": url + "/internal/missing",
                "stub_callback_timeout_seconds": 0.3,
            }
        )
        assert Delivery(settings, gateway.sessions).deliver_one()
        with gateway.sessions.begin() as session:
            row = session.get(Operation, UUID(payment["external_operation_id"]))
            assert row.delivery_pending
            row.next_delivery_at = session.scalar(select(func.clock_timestamp()))
        settings = settings.model_copy(
            update={"payment_callback_url": url + "/internal/payment-events"}
        )
        assert Delivery(settings, gateway.sessions).deliver_one()
    with gateway.sessions() as session:
        assert not session.get(Operation, UUID(payment["external_operation_id"])).delivery_pending
    with database.sessions() as session:
        assert session.get(Payment, UUID(payment["id"])).status == "succeeded"
        assert session.scalar(select(func.count()).select_from(PaymentNotification)) == 2


def test_automatic_delivery_works_without_open_payment_card(
    client, actors, ready, gateway, database
):
    _request, booking = ready
    payment = create(client, actors, booking).json()
    with serve(create_app(gateway.crm_settings)) as url:
        settings = gateway.stub_settings.model_copy(
            update={
                "payment_callback_url": url + "/internal/payment-events",
                "stub_delivery_interval_seconds": 0.05,
                "stub_callback_timeout_seconds": 0.3,
            }
        )
        with serve(create_stub(settings)):
            assert gateway.outcome(payment, "succeeded").status_code == 200

            def delivered():
                with database.sessions() as session:
                    return session.get(Payment, UUID(payment["id"])).status == "succeeded"

            eventually(delivered)
    assert notices(client, actors).json()["unread_count"] == 1


def test_background_reconciliation_recovers_without_callback(
    client, actors, ready, gateway, database
):
    _request, booking = ready
    payment = create(client, actors, booking).json()
    assert gateway.outcome(payment, "succeeded").status_code == 200
    settings = gateway.crm_settings.model_copy(
        update={
            "payment_reconciliation_enabled": True,
            "payment_reconciliation_interval_seconds": 0.05,
        }
    )
    with TestClient(create_app(settings)):

        def reconciled():
            with database.sessions() as session:
                return session.get(Payment, UUID(payment["id"])).status == "succeeded"

        eventually(reconciled)
    assert notices(client, actors).json()["unread_count"] == 1


def test_reconciliation_schedule_survives_worker_restart(
    client, actors, ready, gateway, database, application
):
    _request, booking = ready
    payment = create(client, actors, booking).json()
    first = Reconciler(database, application.state.payment_adapter)
    assert first.reconcile_one()
    with database.sessions() as session:
        row = session.get(Payment, UUID(payment["id"]))
        assert row.next_reconcile_at > session.scalar(select(func.clock_timestamp()))
    second = Reconciler(database, application.state.payment_adapter)
    assert not second.reconcile_one()


def test_background_reconciliation_waits_after_timeout_then_recovers(
    client, actors, ready, gateway, database
):
    _request, booking = ready
    payment = create(client, actors, booking).json()
    assert gateway.outcome(payment, "timeout").status_code == 200
    settings = gateway.crm_settings.model_copy(
        update={
            "payment_reconciliation_enabled": True,
            "payment_reconciliation_interval_seconds": 0.05,
        }
    )
    with TestClient(create_app(settings)):

        def timed_out():
            with database.sessions() as session:
                row = session.get(Payment, UUID(payment["id"]))
                return row.status == "pending" and "вовремя" in (row.pending_reason or "")

        eventually(timed_out)
        assert gateway.outcome(payment, "succeeded").status_code == 200

        def recovered():
            with database.sessions() as session:
                return session.get(Payment, UUID(payment["id"])).status == "succeeded"

        eventually(recovered)


def test_notification_and_financial_pages_have_bounded_queries(client, actors, paid, application):
    from sqlalchemy import event

    statements = []

    def capture(_connection, _cursor, statement, *_args):
        statements.append(statement)

    engine = application.state.database.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert notices(client, actors).status_code == 200 and len(statements) <= 3
        statements.clear()
        assert (
            client.get("/api/financial-bookings", headers=actors["head"]["headers"]).status_code
            == 200
            and len(statements) <= 5
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_only_current_recipient_can_mark_notification_under_concurrent_reads(
    client, actors, paid, gateway
):
    identity = notices(client, actors).json()["items"][0]["id"]
    barrier = Barrier(2)

    def run(_index):
        with TestClient(create_app(gateway.crm_settings)) as connection:
            barrier.wait(timeout=15)
            return mark(connection, actors, identity)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(run, range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json()["read_at"] == responses[1].json()["read_at"]
