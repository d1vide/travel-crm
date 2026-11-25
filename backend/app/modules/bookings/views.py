from sqlalchemy import select

from app.modules.bookings.models import BookingStatus, BookingTourist
from app.modules.bookings.schemas import Booking as BookingDto
from app.modules.bookings.schemas import BookingTourist as TouristDto
from app.modules.requests.schemas import BookingSummary, OfferSnapshot


def summary(row):
    return BookingSummary(
        id=row.id,
        status=row.status,
        total_amount=f"{row.total_amount:.2f}",
        currency=row.currency,
        paid_amount="0.00",
        remaining_amount=f"{row.total_amount:.2f}",
    )


def project(session, rows):
    ids = [row.id for row in rows]
    if not ids:
        return []
    tourists = {identity: [] for identity in ids}
    for item in session.scalars(
        select(BookingTourist)
        .where(BookingTourist.booking_id.in_(ids))
        .order_by(BookingTourist.position, BookingTourist.id)
    ):
        tourists[item.booking_id].append(
            TouristDto(tourist_id=item.tourist_id, tourist_snapshot=item.tourist_snapshot)
        )
    return [
        BookingDto(
            id=row.id,
            request_id=row.request_id,
            selection_item_id=row.selection_item_id,
            offer_snapshot=OfferSnapshot.model_validate(row.offer_snapshot),
            total_amount=f"{row.total_amount:.2f}",
            currency=row.currency,
            status=row.status,
            supplier_booking_number=row.supplier_booking_number,
            rejection_reason=row.rejection_reason,
            cancellation_reason=row.cancellation_reason,
            cancellation_response=row.cancellation_response,
            confirmed_at=row.confirmed_at,
            cancelled_at=row.cancelled_at,
            paid_amount="0.00",
            reserved_payment_amount="0.00",
            remaining_amount=f"{row.total_amount:.2f}",
            available_payment_amount=f"{row.total_amount:.2f}"
            if row.status == BookingStatus.CONFIRMED
            else "0.00",
            refunded_amount="0.00",
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
            tourists=tourists[row.id],
            allowed_actions=["confirm", "reject"] if row.status == BookingStatus.PENDING else [],
        )
        for row in rows
    ]
