from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, null

from app.modules.bookings.models import Booking
from app.modules.payments.models import Payment, Refund
from app.modules.requests.models import TravelRequest
from tests.payment_gateway import gateway as gateway
from tests.test_bookings import context as context
from tests.test_clients import actors as actors
from tests.test_clients import validate
from tests.test_payments import ready as ready
from tests.test_refunds import cancelled as cancelled
from tests.test_refunds import create as refund

START = datetime(2026, 11, 25, 21, tzinfo=UTC)
END = START + timedelta(days=1)


def read(client, actors, **params):
    return client.get(
        "/api/reports/summary",
        params={"date_from": "2026-11-26", "date_to": "2026-11-26", **params},
        headers=actors["head"]["headers"],
    )


@pytest.fixture
def facts(client, actors, cancelled, database):
    request, booking, payment = cancelled
    returned = refund(client, actors, payment).json()
    with database.sessions.begin() as session:
        rows = (
            session.get(TravelRequest, UUID(request["id"])),
            session.get(Booking, UUID(booking["id"])),
            session.get(Payment, UUID(payment["id"])),
            session.get(Refund, UUID(returned["id"])),
        )
        rows[0].created_at = START
        rows[1].confirmed_at = START
        rows[2].succeeded_at = START
        rows[3].succeeded_at = START
    return request, booking, payment, returned


@pytest.mark.parametrize(
    "offset,included",
    [
        (timedelta(microseconds=-1), False),
        (timedelta(0), True),
        (timedelta(days=1, microseconds=-1), True),
        (timedelta(days=1), False),
    ],
)
def test_moscow_boundaries_and_cancelled_confirmation(
    client, actors, facts, database, offset, included
):
    request, booking, payment, returned = facts
    when = START + offset
    with database.sessions.begin() as session:
        session.get(TravelRequest, UUID(request["id"])).created_at = when
        session.get(Booking, UUID(booking["id"])).confirmed_at = when
        session.get(Payment, UUID(payment["id"])).succeeded_at = when
        session.get(Refund, UUID(returned["id"])).succeeded_at = when
    result = read(client, actors)
    assert result.status_code == 200
    validate("Report", result.json())
    assert result.json() == {
        "date_from": "2026-11-26",
        "date_to": "2026-11-26",
        "timezone": "Europe/Moscow",
        "currency": "RUB",
        "requests_created": int(included),
        "bookings_confirmed": int(included),
        "payments_succeeded_amount": "3000.00" if included else "0.00",
        "refunds_succeeded_amount": "1000.00" if included else "0.00",
    }
    assert result.headers["Cache-Control"] == "no-store"


def test_separate_aggregates_and_success_dates(client, actors, facts, database, application):
    _request, booking, _payment, _returned = facts
    with database.sessions.begin() as session:
        paid = Payment(
            booking_id=UUID(booking["id"]),
            amount=2000,
            currency="RUB",
            status="succeeded",
            succeeded_at=START,
            external_operation_id=str(uuid4()),
            pending_reason=null(),
            created_at=START - timedelta(days=30),
        )
        session.add(paid)
        session.flush()
        session.add(
            Refund(
                payment_id=paid.id,
                amount=200,
                currency="RUB",
                status="succeeded",
                succeeded_at=START,
                external_operation_id=str(uuid4()),
                pending_reason=null(),
                created_at=START - timedelta(days=30),
            )
        )
        session.add(
            Refund(
                payment_id=paid.id,
                amount=500,
                currency="RUB",
                status="processing",
                created_at=START,
            )
        )
        session.add(
            Payment(
                booking_id=UUID(booking["id"]),
                amount=500,
                currency="RUB",
                status="failed",
                external_operation_id=str(uuid4()),
                failure_reason="Тестовый отказ",
                pending_reason=null(),
                created_at=START,
            )
        )
    statements = []

    def capture(_connection, _cursor, statement, *_args):
        statements.append(statement)

    engine = application.state.database.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = read(client, actors).json()
        assert len(statements) <= 2  # authentication and one consistent aggregate statement
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert result["requests_created"] == result["bookings_confirmed"] == 1
    assert result["payments_succeeded_amount"] == "5000.00"
    assert result["refunds_succeeded_amount"] == "1200.00"


@pytest.mark.parametrize(
    "dates",
    [
        {"date_from": "2026-11-27"},
        {"date_from": "2026-02-30"},
        {"date_from": "20261126"},
        {"date_to": "2026-11-26T00:00:00Z"},
        {"unknown": "1"},
        {"date_from": ""},
    ],
)
def test_invalid_periods(client, actors, dates):
    result = read(client, actors, **dates)
    assert result.status_code == 422
    validate("Error", result.json())


def test_roles_and_required_dates(client, actors):
    for actor in ("manager", "other", "accountant"):
        assert (
            client.get(
                "/api/reports/summary",
                params={"date_from": "2026-11-26", "date_to": "2026-11-26"},
                headers=actors[actor]["headers"],
            ).status_code
            == 403
        )
    assert client.get("/api/reports/summary").status_code == 401
    assert client.get("/api/reports/summary", headers=actors["head"]["headers"]).status_code == 422


@pytest.mark.parametrize(
    "date_from,date_to",
    [("0001-01-01", "0001-01-01"), ("9999-12-31", "9999-12-31"), ("2024-02-29", "2024-02-29")],
)
def test_empty_and_calendar_extremes(client, actors, date_from, date_to):
    result = read(client, actors, date_from=date_from, date_to=date_to)
    assert result.status_code == 200
    assert result.json()["requests_created"] == result.json()["bookings_confirmed"] == 0
    assert (
        result.json()["payments_succeeded_amount"]
        == result.json()["refunds_succeeded_amount"]
        == "0.00"
    )
