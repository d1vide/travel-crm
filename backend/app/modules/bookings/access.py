from sqlalchemy import select

from app.core.errors import ApiError
from app.modules.bookings.models import ACTIVE_STATUSES, Booking


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
