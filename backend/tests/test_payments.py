from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Event
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from stubs.store import Operation

from app.core.audit import AuditRecord
from app.main import create_app
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.payments import service
from app.modules.payments.adapter import ProviderError
from app.modules.payments.models import Payment, PaymentNotification
from tests.payment_gateway import gateway as gateway
from tests.test_bookings import card as booking_card
from tests.test_bookings import command as booking_command
from tests.test_bookings import context as context
from tests.test_clients import actors as actors
from tests.test_clients import validate
from tests.test_requests import write
from tests.test_selections import read_request


@pytest.fixture
def ready(client, actors, context):
    request, _selection, _link = context
    from tests.test_bookings import create

    pending = create(client, actors, request).json()
    response = booking_command(
        client, actors, pending, "confirm", supplier_booking_number="DEMO-PAYMENT-15"
    )
    assert response.status_code == 200
    return request, response.json()


def create(client, actors, booking, amount="1000.00", *, key=None, actor="manager", **changes):
    return write(
        client,
        actors,
        "POST",
        f"/api/bookings/{booking['id']}/payments",
        {"version": booking["version"], "amount": amount, "currency": "RUB", **changes},
        actor,
        key,
    )


def read(client, actors, identity, actor="manager"):
    return client.get(f"/api/payments/{identity}", headers=actors[actor]["headers"])


def reconcile(client, actors, identity, actor="manager"):
    return client.post(f"/api/payments/{identity}/reconcile", headers=actors[actor]["headers"])


def test_payment_checkout_success_and_atomic_accounting(client, actors, ready, gateway, database):
    request, booking = ready
    response = create(client, actors, booking)
    assert response.status_code == 202
    assert response.headers["Cache-Control"] == "no-store"
    payment = response.json()
    validate("Payment", payment)
    assert (
        payment["status"] == "pending"
        and payment["external_operation_id"]
        and payment["payment_url"]
    )
    assert payment["allowed_actions"] == ["reconcile"] and payment["can_open_request"]
    current = booking_card(client, actors, booking["id"]).json()
    assert current["paid_amount"] == "0.00" and current["reserved_payment_amount"] == "1000.00"
    assert Decimal(current["available_payment_amount"]) == Decimal(booking["total_amount"]) - 1000
    with httpx.Client(trust_env=False) as connection:
        page = connection.get(gateway.url + urlsplit(payment["payment_url"]).path)
    assert page.status_code == 200 and page.headers["Referrer-Policy"] == "no-referrer"
    assert 'name="outcome"' in page.text and "card_number" not in page.text
    assert gateway.outcome(payment, "succeeded").status_code == 200
    success = read(client, actors, payment["id"])
    assert success.status_code == 200
    validate("Payment", success.json())
    assert success.json()["status"] == "succeeded" and success.json()["succeeded_at"].endswith("Z")
    assert success.json()["pending_reason"] is None and success.json()["allowed_actions"] == []
    for _ in range(2):
        assert reconcile(client, actors, payment["id"]).json() == success.json()
    current = booking_card(client, actors, booking["id"]).json()
    assert current["paid_amount"] == "1000.00" and current["reserved_payment_amount"] == "0.00"
    assert Decimal(current["remaining_amount"]) == Decimal(booking["total_amount"]) - 1000
    assert current["version"] == booking["version"] + 2
    request = read_request(client, actors, request["id"])
    assert request["active_booking"]["paid_amount"] == "1000.00"
    with database.sessions() as session:
        notices = session.scalars(
            select(PaymentNotification).where(PaymentNotification.payment_id == UUID(payment["id"]))
        ).all()
        assert {row.recipient_id for row in notices} == {
            actors["manager"]["id"],
            actors["head"]["id"],
        }
        events = session.scalars(
            select(AuditRecord).where(AuditRecord.entity_type == "payment")
        ).all()
        assert len(events) == 2 and events[-1].source in ("staff", "payment_service")


def test_full_payment_closes_available_balance(client, actors, ready, gateway):
    request, booking = ready
    payment = create(client, actors, booking, booking["total_amount"]).json()
    current = booking_card(client, actors, booking["id"]).json()
    assert (
        current["available_payment_amount"] == "0.00"
        and "create_payment" not in current["allowed_actions"]
    )
    assert create(client, actors, current, "0.01").json()["code"] == "payment_limit_exceeded"
    assert gateway.outcome(payment, "succeeded").status_code == 200
    assert read(client, actors, payment["id"]).json()["status"] == "succeeded"
    current = booking_card(client, actors, booking["id"]).json()
    assert (
        current["paid_amount"] == booking["total_amount"] and current["remaining_amount"] == "0.00"
    )
    assert "complete" not in read_request(client, actors, request["id"])["allowed_actions"]


def test_decline_releases_reserve_and_new_attempt_is_separate(client, actors, ready, gateway):
    _request, booking = ready
    first = create(client, actors, booking).json()
    assert gateway.outcome(first, "failed").status_code == 200
    failed = reconcile(client, actors, first["id"]).json()
    assert (
        failed["status"] == "failed" and failed["failure_reason"] and failed["succeeded_at"] is None
    )
    current = booking_card(client, actors, booking["id"]).json()
    assert current["reserved_payment_amount"] == "0.00" and current["paid_amount"] == "0.00"
    second = create(client, actors, current)
    assert second.status_code == 202 and second.json()["id"] != first["id"]
    with gateway.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Operation)) == 2


def test_real_http_timeout_keeps_reserve_and_later_reconcile_succeeds(
    client, actors, ready, gateway
):
    _request, booking = ready
    payment = create(client, actors, booking).json()
    assert gateway.outcome(payment, "timeout").status_code == 200
    waiting = reconcile(client, actors, payment["id"])
    assert waiting.status_code == 202 and waiting.json()["status"] == "pending"
    assert "вовремя" in waiting.json()["pending_reason"]
    assert (
        booking_card(client, actors, booking["id"]).json()["reserved_payment_amount"] == "1000.00"
    )
    assert gateway.outcome(payment, "succeeded").status_code == 200
    assert reconcile(client, actors, payment["id"]).json()["status"] == "succeeded"


def test_lost_create_response_recovers_after_service_restart(
    client, actors, ready, gateway, application, database
):
    _request, booking = ready
    key = uuid4()
    original = application.state.payment_adapter.fetch

    def lose_response(*args):
        original(*args)
        raise ProviderError("Платёжный сервис не ответил вовремя; требуется сверка")

    application.state.payment_adapter.fetch = lose_response
    first = create(client, actors, booking, key=key)
    assert first.status_code == 202 and first.json()["payment_url"] is None
    with gateway.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Operation)) == 1
    gateway.restart()
    with TestClient(create_app(gateway.crm_settings)) as connection:
        replay = create(connection, actors, booking, key=key)
    assert (
        replay.status_code == 202
        and replay.json()["id"] == first.json()["id"]
        and replay.json()["payment_url"]
    )
    with gateway.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Operation)) == 1
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": "0.00"},
        {"amount": "-1.00"},
        {"amount": 1000},
        {"amount": "1.001"},
        {"currency": "USD"},
        {"version": True},
        {"status": "succeeded"},
        {"card_number": "FICTIONAL-NOT-A-CARD"},
    ],
)
def test_invalid_commands_never_reserve_funds(client, actors, ready, gateway, database, changes):
    _request, booking = ready
    response = create(client, actors, booking, **changes)
    assert response.status_code == 422
    validate("Error", response.json())
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 0
    with gateway.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Operation)) == 0


def test_limit_version_and_booking_state_checks(client, actors, ready, gateway, database):
    _request, booking = ready
    assert (
        create(client, actors, booking, str(Decimal(booking["total_amount"]) + 1)).json()["code"]
        == "payment_limit_exceeded"
    )
    assert (
        create(client, actors, booking, version=booking["version"] - 1).json()["code"]
        == "version_conflict"
    )
    with database.sessions.begin() as session:
        row = session.get(Booking, UUID(booking["id"]))
        row.status = BookingStatus.CANCELLATION_REQUESTED
    assert create(client, actors, booking).json()["code"] == "invalid_transition"


def test_roles_lists_filters_and_current_access(client, actors, ready, gateway):
    request, booking = ready
    key = uuid4()
    payment = create(client, actors, booking, key=key).json()
    assert client.get("/api/payments", headers=actors["manager"]["headers"]).status_code == 403
    for actor in ("head", "accountant"):
        response = client.get(
            "/api/payments",
            params={"booking_id": booking["id"], "status": "pending"},
            headers=actors[actor]["headers"],
        )
        assert response.status_code == 200 and response.json()["total"] == 1
        validate("PaymentPage", response.json())
    accountant = read(client, actors, payment["id"], "accountant").json()
    assert not accountant["can_open_request"] and accountant["allowed_actions"] == []
    assert reconcile(client, actors, payment["id"], "accountant").status_code == 403
    assert create(client, actors, booking, actor="accountant").status_code == 403
    assert (
        read(client, actors, payment["id"], "other").json() == read(client, actors, uuid4()).json()
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
    assert read(client, actors, payment["id"]).status_code == 404
    assert create(client, actors, booking, key=key).status_code == 404
    assert read(client, actors, payment["id"], "other").status_code == 200
    assert gateway.outcome(payment, "succeeded").status_code == 200
    assert read(client, actors, payment["id"], "other").json()["status"] == "succeeded"


@pytest.mark.parametrize("mode", ["same_key", "different_keys", "same_result"])
def test_concurrent_requests_preserve_money_invariants(
    client, actors, ready, gateway, database, mode
):
    _request, booking = ready
    barrier, key = Barrier(2), uuid4()
    payment = (
        create(client, actors, booking, booking["total_amount"]).json()
        if mode == "same_result"
        else None
    )
    if payment:
        assert gateway.outcome(payment, "succeeded").status_code == 200

    def run(_index):
        with TestClient(create_app(gateway.crm_settings)) as connection:
            barrier.wait(timeout=20)
            return (
                reconcile(connection, actors, payment["id"])
                if payment
                else create(
                    connection,
                    actors,
                    booking,
                    booking["total_amount"],
                    key=key if mode == "same_key" else uuid4(),
                )
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(run, range(2)))
    assert sorted(response.status_code for response in responses) == (
        [202, 409] if mode == "different_keys" else [202, 202]
    )
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 1
        if payment:
            assert session.scalar(select(func.count()).select_from(PaymentNotification)) == 2
    with gateway.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Operation)) == 1


def test_provider_rejects_unauthorized_and_conflicting_replay(client, actors, ready, gateway):
    _request, booking = ready
    payment = create(client, actors, booking).json()
    with httpx.Client(base_url=gateway.url, trust_env=False) as connection:
        assert connection.get(f"/v1/payments/{payment['external_operation_id']}").status_code == 401
        response = connection.post(
            "/v1/payments",
            json={"client_operation_id": payment["id"], "amount": "1.00", "currency": "RUB"},
            headers={
                "Authorization": "Bearer "
                + gateway.stub_settings.payment_stub_key.get_secret_value()
            },
        )
        assert response.status_code == 409
        assert (
            connection.post(
                urlsplit(payment["payment_url"]).path,
                data={"outcome": "succeeded"},
                headers={"Origin": "https://other.example"},
            ).status_code
            == 403
        )
    assert gateway.outcome(payment, "succeeded").status_code == 200
    assert gateway.outcome(payment, "failed").status_code == 409


def test_mismatched_and_conflicting_provider_results_do_not_change_money(
    client, actors, ready, gateway, database
):
    _request, booking = ready
    payment = create(client, actors, booking).json()
    data = gateway.adapter.fetch(
        UUID(payment["id"]), payment["external_operation_id"], Decimal(payment["amount"]), "RUB"
    )
    with database.sessions() as session:
        service.apply_result(
            session,
            UUID(payment["id"]),
            data.model_copy(update={"amount": "999999.00"}),
            None,
            gateway.adapter,
        )
    with database.sessions() as session:
        assert session.get(Payment, UUID(payment["id"])).status == "pending"
    assert gateway.outcome(payment, "succeeded").status_code == 200
    saved = read(client, actors, payment["id"]).json()
    with database.sessions() as session:
        service.apply_result(session, UUID(payment["id"]), data, None, gateway.adapter)
    with database.sessions() as session:
        assert not session.get(Payment, UUID(payment["id"])).provider_conflict
    with database.sessions() as session:
        service.apply_result(
            session,
            UUID(payment["id"]),
            data.model_copy(update={"status": "failed", "failure_reason": "Учебный отказ"}),
            None,
            gateway.adapter,
        )
    assert read(client, actors, payment["id"]).json() == saved


def test_database_guards_positive_amount_and_unique_provider_id(
    client, actors, ready, gateway, database
):
    _request, booking = ready
    payment = create(client, actors, booking).json()
    for changes in (
        {"amount": Decimal(0)},
        {"currency": "USD"},
        {"status": "succeeded"},
        {"external_operation_id": payment["external_operation_id"]},
    ):
        with pytest.raises(IntegrityError), database.sessions.begin() as session:
            session.add(
                Payment(
                    booking_id=UUID(booking["id"]),
                    amount=Decimal("1.00"),
                    **{k: v for k, v in changes.items() if k != "amount"},
                )
                if "amount" not in changes
                else Payment(booking_id=UUID(booking["id"]), amount=changes["amount"])
            )
            session.flush()


def test_network_call_releases_locks_and_rechecks_access(
    client, actors, ready, gateway, application, database
):
    request, booking = ready
    entered, proceed = Event(), Event()
    original = application.state.payment_adapter.fetch

    def wait_for_reassignment(*args):
        entered.set()
        assert proceed.wait(timeout=15)
        return original(*args)

    application.state.payment_adapter.fetch = wait_for_reassignment
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(create, client, actors, booking)
        try:
            assert entered.wait(timeout=15)
            with database.sessions.begin() as session:
                row = session.scalar(
                    select(Booking)
                    .where(Booking.id == UUID(booking["id"]))
                    .with_for_update(nowait=True)
                )
                assert row.version == booking["version"] + 1
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
        finally:
            proceed.set()
        assert future.result(timeout=20).status_code == 404
    with database.sessions() as session:
        identity = session.scalar(select(Payment.id))
    assert read(client, actors, identity, "other").status_code == 200


def test_two_partial_payments_use_one_shared_balance(client, actors, ready, gateway, database):
    _request, booking = ready
    first = create(client, actors, booking).json()
    current = booking_card(client, actors, booking["id"]).json()
    second = create(
        client, actors, current, f"{Decimal(booking['total_amount']) - 1000:.2f}"
    ).json()
    assert gateway.outcome(first, "succeeded").status_code == 200
    assert gateway.outcome(second, "succeeded").status_code == 200
    assert read(client, actors, second["id"]).json()["status"] == "succeeded"
    assert read(client, actors, first["id"]).json()["status"] == "succeeded"
    current = booking_card(client, actors, booking["id"]).json()
    assert (
        current["paid_amount"] == booking["total_amount"]
        and current["remaining_amount"] == current["reserved_payment_amount"] == "0.00"
    )
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(PaymentNotification)) == 4


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", "1.00"),
        ("client_operation_id", str(uuid4())),
        ("id", str(uuid4())),
        ("currency", "USD"),
        ("status", "unknown"),
    ],
)
def test_adapter_rejects_mismatched_http_results(
    client, actors, ready, gateway, monkeypatch, field, value
):
    _request, booking = ready
    payment = create(client, actors, booking).json()
    result = gateway.adapter.fetch(
        UUID(payment["id"]), payment["external_operation_id"], Decimal(payment["amount"]), "RUB"
    ).model_dump(mode="json")
    external_id = result["id"]
    result[field] = value
    client_type = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=result))
    with monkeypatch.context() as patch:
        patch.setattr(
            "app.modules.payments.adapter.httpx.Client",
            lambda **kwargs: client_type(**kwargs, transport=transport),
        )
        with pytest.raises(ProviderError):
            gateway.adapter.fetch(
                UUID(payment["id"]),
                external_id,
                Decimal(payment["amount"]),
                "RUB",
            )


def test_stub_migration_roundtrip_and_reapply(gateway):
    from pathlib import Path

    from alembic.config import Config
    from stubs.migrate import upgrade

    from alembic import command

    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "stubs/migrations")
    )
    config.attributes["settings"] = gateway.stub_settings
    command.downgrade(config, "base")
    upgrade(gateway.stub_settings)
    upgrade(gateway.stub_settings)
    command.check(config)
