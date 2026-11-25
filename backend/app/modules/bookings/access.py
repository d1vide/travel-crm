from sqlalchemy import or_, select

from app.core.errors import ApiError
from app.modules.bookings.models import ACTIVE_STATUSES, Booking
from app.modules.payments.models import Payment, Refund


def active_condition(request_id):
    return (
        select(Booking.id)
        .where(Booking.request_id == request_id, Booking.status.in_(ACTIVE_STATUSES))
        .exists()
    )


def ensure_no_active(session, identity):
    if session.scalar(select(active_condition(identity))):
        raise ApiError(409, "invalid_transition", "Операция недоступна при действующей брони")


def active_bookings(session, rows):
    ids = [row.id for row in rows if row.status != "new"]
    return (
        {
            row.request_id: row
            for row in session.scalars(
                select(Booking).where(
                    Booking.request_id.in_(ids), Booking.status.in_(ACTIVE_STATUSES)
                )
            )
        }
        if ids
        else {}
    )


def pending_request_ids(session, identities):
    if not identities:
        return set()
    return set(
        session.scalars(
            select(Booking.request_id)
            .join(Payment, Payment.booking_id == Booking.id)
            .outerjoin(Refund, Refund.payment_id == Payment.id)
            .where(
                Booking.request_id.in_(identities),
                or_(Payment.status == "pending", Refund.status == "processing"),
            )
            .distinct()
        )
    )
