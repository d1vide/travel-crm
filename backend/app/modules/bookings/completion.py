from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.core.audit import record_request_change
from app.core.errors import ApiError
from app.core.idempotency import find_previous
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.payments.refund_views import booking_totals
from app.modules.payments.views import totals
from app.modules.requests.models import RequestStatus


def business_date(session):
    return session.scalar(select(func.timezone("Europe/Moscow", func.clock_timestamp()))).date()


def eligible(booking, money, today, refunds=(Decimal(0), Decimal(0))):
    paid, reserved = money
    return (
        booking.status == BookingStatus.CONFIRMED
        and paid == booking.total_amount
        and reserved == 0
        and sum(refunds) == 0
        and today > date.fromisoformat(booking.offer_snapshot["ends_on"])
    )


def complete(session, actor, identity, body, command):
    from app.modules.requests import service as requests

    requests.get_visible(session, actor, identity)
    operation = f"POST /api/requests/{identity}/actions/complete"
    previous = find_previous(session, f"staff:{actor.id}", operation, command)
    if previous is not None:
        return requests.replay(session, actor, previous, command)
    request = requests.locked_request(session, actor, identity)
    requests.expect_version(request, body.version)
    if request.status != RequestStatus.BOOKED:
        requests.invalid_transition()
    booking = session.scalar(
        select(Booking)
        .where(Booking.request_id == identity, Booking.status == BookingStatus.CONFIRMED)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if booking is None or booking.selection_item_id != request.selected_selection_item_id:
        requests.invalid_transition()
    money = totals(session, [booking.id]).get(booking.id, (Decimal(0), Decimal(0)))
    refunded = booking_totals(session, [booking.id]).get(booking.id, (Decimal(0), Decimal(0)))
    if not eligible(booking, money, business_date(session), refunded):
        raise ApiError(
            409,
            "invalid_transition",
            "Завершение доступно после окончания тура и полной оплаты без ожидающих операций",
        )
    record_request_change(
        session,
        request,
        actor,
        "request_status",
        request.status,
        RequestStatus.COMPLETED,
        "completed",
    )
    request.status = RequestStatus.COMPLETED
    request.completed_at = session.scalar(select(func.clock_timestamp()))
    request.version += 1
    return requests.finish(session, actor, request, operation, command)
