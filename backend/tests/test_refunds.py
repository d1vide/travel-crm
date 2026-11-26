from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from stubs.store import RefundOperation

from app.core.audit import AuditRecord
from app.main import create_app
from app.modules.payments import refunds
from app.modules.payments.adapter import ProviderRefund
from app.modules.payments.models import Payment, Refund
from app.modules.payments.reconciliation import Reconciler
from tests.live_http import eventually, serve
from tests.payment_gateway import gateway as gateway
from tests.test_booking_cancellation import ask, confirm
from tests.test_bookings import card as booking_card
from tests.test_bookings import context as context
from tests.test_clients import actors as actors
from tests.test_clients import validate
from tests.test_payments import create as pay
from tests.test_payments import read as payment_card
from tests.test_payments import ready as ready
from tests.test_requests import action, write
from tests.test_selections import read_request


@pytest.fixture
def cancelled(client, actors, ready, gateway):
    request, booking = ready
    payment = pay(client, actors, booking, "3000.00").json()
    gateway.outcome(payment, "succeeded")
    payment = payment_card(client, actors, payment["id"]).json()
    booking = booking_card(client, actors, booking["id"]).json()
    booking = confirm(client, actors, ask(client, actors, booking).json()).json()
    return request, booking, payment


def create(client, actors, payment, amount="1000.00", *, actor="manager", key=None, **changes):
    return write(
        client,
        actors,
        "POST",
        f"/api/payments/{payment['id']}/refunds",
        {"amount": amount, "currency": "RUB", **changes},
        actor,
        key,
    )


def read(client, actors, identity, actor="manager"):
    return client.get(f"/api/refunds/{identity}", headers=actors[actor]["headers"])


def choose(gateway, refund, outcome):
    with gateway.sessions() as session:
        identity = session.scalar(
            select(RefundOperation.id).where(
                RefundOperation.client_operation_id == UUID(refund["id"])
            )
        )
    with httpx.Client(trust_env=False) as connection:
        return connection.post(
            gateway.url + f"/v1/refunds/{identity}/outcome",
            json={"outcome": outcome},
            headers={
                "Authorization": "Bearer "
                + gateway.stub_settings.payment_stub_key.get_secret_value()
            },
        )


def test_partial_full_refunds_update_all_projections_and_history(
    client, actors, cancelled, database
):
    request, booking, payment = cancelled
    before = payment_card(client, actors, payment["id"]).json()
    assert before["available_refund_amount"] == "3000.00" and before["allowed_actions"] == [
        "create_refund"
    ]
    key = uuid4()
    first = create(client, actors, payment, key=key)
    assert first.status_code == 202 and first.json()["status"] == "succeeded"
    validate("Refund", first.json())
    assert first.headers["Cache-Control"] == "no-store"
    assert create(client, actors, payment, key=key).json() == first.json()
    assert (
        create(client, actors, payment, "1001.00", key=key).json()["code"] == "idempotency_conflict"
    )
    assert create(client, actors, payment, "2000.00").json()["status"] == "succeeded"
    assert create(client, actors, payment).json()["code"] == "refund_limit_exceeded"
    after = payment_card(client, actors, payment["id"]).json()
    assert after["status"] == "succeeded" and after["refunded_amount"] == "3000.00"
    assert after["reserved_refund_amount"] == after["available_refund_amount"] == "0.00"
    updated = booking_card(client, actors, booking["id"]).json()
    assert updated["paid_amount"] == updated["refunded_amount"] == "3000.00"
    assert updated["version"] == booking["version"] + 4 and updated["status"] == "cancelled"
    finance = client.get("/api/financial-bookings", headers=actors["accountant"]["headers"]).json()
    assert finance["items"][0]["refunded_amount"] == "3000.00"
    assert read_request(client, actors, request["id"])["status"] == "cancelled"
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Refund)) == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditRecord)
                .where(AuditRecord.action == "refund_succeeded")
            )
            == 2
        )
    history = client.get(
        f"/api/requests/{request['id']}/history", headers=actors["manager"]["headers"]
    )
    validate("AuditRecordPage", history.json())


@pytest.mark.parametrize("outcome", ["failed", "timeout"])
def test_failed_and_timeout_keep_distinct_reservations(client, actors, cancelled, gateway, outcome):
    request, _booking, payment = cancelled
    gateway.stub_settings.stub_refund_outcome = outcome
    response = create(client, actors, payment, "3000.00")
    assert response.status_code == 202
    row = response.json()
    assert row["status"] == ("failed" if outcome == "failed" else "processing")
    current = payment_card(client, actors, payment["id"]).json()
    if outcome == "timeout":
        assert row["external_operation_id"] is None and row["pending_reason"]
        assert (
            current["reserved_refund_amount"] == "3000.00"
            and current["available_refund_amount"] == "0.00"
        )
        assert create(client, actors, payment).json()["code"] == "refund_limit_exceeded"
        request = read_request(client, actors, request["id"])
        assert "resume" not in request["allowed_actions"]
        assert action(client, actors, request, "resume").json()["code"] == "invalid_transition"
        assert choose(gateway, row, "succeeded").status_code == 200
        recovered = read(client, actors, row["id"]).json()
        assert recovered["status"] == "succeeded"
        assert "resume" in read_request(client, actors, request["id"])["allowed_actions"]
    else:
        assert row["failure_reason"] and current["available_refund_amount"] == "3000.00"
        gateway.stub_settings.stub_refund_outcome = "succeeded"
        assert create(client, actors, payment, "3000.00").json()["status"] == "succeeded"


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": "0.00"},
        {"amount": "-1.00"},
        {"amount": 1},
        {"amount": "1.001"},
        {"amount": "1e3"},
        {"currency": "USD"},
        {"status": "succeeded"},
        {"version": 1},
    ],
)
def test_refund_validation(client, actors, cancelled, changes):
    assert create(client, actors, cancelled[2], **changes).status_code == 422


def test_refund_requires_cancelled_booking_and_successful_payment(client, actors, ready, gateway):
    _request, booking = ready
    payment = pay(client, actors, booking).json()
    assert create(client, actors, payment).json()["code"] == "invalid_transition"
    gateway.outcome(payment, "succeeded")
    payment_card(client, actors, payment["id"])
    assert create(client, actors, payment).json()["code"] == "invalid_transition"


def test_roles_lists_privacy_and_reassignment(client, actors, cancelled):
    request, booking, payment = cancelled
    assert create(client, actors, payment, actor="accountant").status_code == 403
    assert create(client, actors, payment, actor="other").status_code == 404
    key = uuid4()
    refund = create(client, actors, payment, actor="head", key=key).json()
    accountant = read(client, actors, refund["id"], "accountant")
    assert accountant.status_code == 200 and not accountant.json()["can_open_request"]
    assert accountant.json()["allowed_actions"] == []
    assert all(
        field not in accountant.text
        for field in ("document_number", "full_name", "payment_url", "checkout_token")
    )
    assert (
        client.post(
            f"/api/refunds/{refund['id']}/reconcile", headers=actors["accountant"]["headers"]
        ).status_code
        == 403
    )
    assert read(client, actors, refund["id"], "other").status_code == 404
    assert client.get("/api/refunds", headers=actors["manager"]["headers"]).status_code == 403
    page = client.get(
        "/api/refunds",
        params={
            "request_id": request["id"],
            "booking_id": booking["id"],
            "payment_id": payment["id"],
            "status": "succeeded",
        },
        headers=actors["accountant"]["headers"],
    )
    validate("RefundPage", page.json())
    assert page.json()["total"] == 1
    assert (
        client.get(
            f"/api/payments/{payment['id']}/refunds", headers=actors["accountant"]["headers"]
        ).json()["total"]
        == 1
    )
    request = read_request(client, actors, request["id"])
    moved = write(
        client,
        actors,
        "PATCH",
        f"/api/requests/{request['id']}/assignee",
        {"version": request["version"], "manager_id": str(actors["other"]["id"])},
        "head",
    )
    assert moved.status_code == 200 and read(client, actors, refund["id"]).status_code == 404
    assert read(client, actors, refund["id"], "other").status_code == 200


@pytest.mark.parametrize("mode", ["same_key", "different_keys"])
def test_concurrent_refunds_never_exceed_payment(
    client, actors, cancelled, gateway, database, mode
):
    payment = cancelled[2]
    barrier, key = Barrier(2), uuid4()

    def run(_index):
        app = create_app(gateway.crm_settings)
        with TestClient(app) as connection:
            barrier.wait(timeout=20)
            return create(
                connection, actors, payment, "3000.00", key=key if mode == "same_key" else uuid4()
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(run, range(2)))
    assert sorted(response.status_code for response in responses) == (
        [202, 202] if mode == "same_key" else [202, 409]
    )
    with database.sessions() as session:
        assert session.scalar(
            select(func.sum(Refund.amount)).where(Refund.status.in_(("succeeded", "processing")))
        ) == Decimal("3000.00")
        assert session.scalar(select(func.count()).select_from(Refund)) == 1


def test_repeated_and_contradictory_results_do_not_change_first_success(
    client, actors, cancelled, gateway, database
):
    refund = create(client, actors, cancelled[2]).json()
    with database.sessions() as session:
        row = session.get(Refund, UUID(refund["id"]))
        payment = session.get(Payment, row.payment_id)
        data = gateway.adapter.fetch_refund(
            row.id,
            row.external_operation_id,
            payment.external_operation_id,
            row.amount,
            row.currency,
        )
    for result in (
        data,
        data,
        data.model_copy(
            update={"status": "failed", "succeeded_at": None, "failure_reason": "Отказ"}
        ),
    ):
        with database.sessions() as session:
            refunds.apply_result(session, UUID(refund["id"]), result, None)
    assert read(client, actors, refund["id"]).json() == refund
    with database.sessions() as session:
        assert session.get(Refund, UUID(refund["id"])).provider_conflict
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditRecord)
                .where(AuditRecord.action == "refund_succeeded")
            )
            == 1
        )


def test_background_worker_recovers_timeout_without_open_card(
    client, actors, cancelled, gateway, database
):
    gateway.stub_settings.stub_refund_outcome = "timeout"
    row = create(client, actors, cancelled[2]).json()
    assert row["status"] == "processing"
    assert choose(gateway, row, "succeeded").status_code == 200
    first = Reconciler(database, gateway.adapter)
    assert first.reconcile_one(refund=True)
    second = Reconciler(database, gateway.adapter)
    assert not second.reconcile_one(refund=True)
    with database.sessions() as session:
        assert session.get(Refund, UUID(row["id"])).status == "succeeded"


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": "1001.00"},
        {"payment_id": uuid4()},
        {"client_operation_id": uuid4()},
        {"id": uuid4()},
    ],
)
def test_mismatched_results_preserve_processing(
    client, actors, cancelled, gateway, database, changes
):
    gateway.stub_settings.stub_refund_outcome = "timeout"
    row = create(client, actors, cancelled[2]).json()
    choose(gateway, row, "succeeded")
    with gateway.sessions() as session:
        external = session.scalar(
            select(RefundOperation).where(RefundOperation.client_operation_id == UUID(row["id"]))
        )
        from stubs.refunds import dto

        payload = dto(external)
    # First bind the known external operation to test an inconsistent external ID.
    with database.sessions.begin() as session:
        session.get(Refund, UUID(row["id"])).external_operation_id = payload["id"]
    data = ProviderRefund.model_validate({**payload, **changes})
    with database.sessions() as session:
        refunds.apply_result(session, UUID(row["id"]), data, None)
    with database.sessions() as session:
        assert session.get(Refund, UUID(row["id"])).status == "processing"


def test_reassignment_during_provider_call_keeps_fact_and_hides_response(
    client, actors, cancelled, gateway, database, monkeypatch
):
    request, _booking, payment = cancelled
    original = gateway.adapter.fetch_refund

    def moved(*args):
        result = original(*args)
        current = read_request(client, actors, request["id"])
        response = write(
            client,
            actors,
            "PATCH",
            f"/api/requests/{request['id']}/assignee",
            {"version": current["version"], "manager_id": str(actors["other"]["id"])},
            "head",
        )
        assert response.status_code == 200
        return result

    monkeypatch.setattr(gateway.adapter, "fetch_refund", moved)
    key = uuid4()
    assert create(client, actors, payment, key=key).status_code == 404
    assert create(client, actors, payment, key=key).status_code == 404
    with database.sessions() as session:
        row = session.scalar(select(Refund))
        assert row.status == "succeeded"
        identity = row.id
    assert read(client, actors, identity, "other").json()["status"] == "succeeded"


def test_lifespan_worker_finishes_refund_without_card(client, actors, cancelled, gateway, database):
    gateway.stub_settings.stub_refund_outcome = "timeout"
    row = create(client, actors, cancelled[2]).json()
    assert choose(gateway, row, "succeeded").status_code == 200
    configuration = gateway.crm_settings.model_copy(
        update={
            "payment_reconciliation_enabled": True,
            "payment_reconciliation_interval_seconds": 0.05,
        }
    )

    def succeeded():
        with database.sessions() as session:
            return session.get(Refund, UUID(row["id"])).status == "succeeded"

    with serve(create_app(configuration)):
        eventually(succeeded)


def test_stub_enforces_own_refund_limits_and_authentication(client, actors, cancelled, gateway):
    payment = cancelled[2]
    payload = {
        "client_operation_id": str(uuid4()),
        "payment_id": payment["external_operation_id"],
        "amount": "2000.00",
        "currency": "RUB",
    }
    with httpx.Client(base_url=gateway.url, trust_env=False) as connection:
        assert connection.post("/v1/refunds", json=payload).status_code == 401
        connection.headers["Authorization"] = (
            "Bearer " + gateway.stub_settings.payment_stub_key.get_secret_value()
        )
        first = connection.post("/v1/refunds", json=payload)
        assert first.status_code == 200
        assert connection.post("/v1/refunds", json=payload).json() == first.json()
        assert (
            connection.post("/v1/refunds", json={**payload, "amount": "1000.00"}).status_code == 409
        )
        assert (
            connection.post(
                "/v1/refunds", json={**payload, "client_operation_id": str(uuid4())}
            ).status_code
            == 409
        )
        assert (
            connection.post(
                "/v1/refunds/" + first.json()["id"] + "/outcome", json={"outcome": "failed"}
            ).status_code
            == 409
        )
