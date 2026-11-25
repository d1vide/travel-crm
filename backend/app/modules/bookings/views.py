from decimal import Decimal

from sqlalchemy import select

from app.modules.bookings.completion import business_date, eligible
from app.modules.bookings.models import BookingStatus, BookingTourist
from app.modules.bookings.schemas import Booking as BookingDto
from app.modules.bookings.schemas import BookingTourist as TouristDto
from app.modules.payments.views import totals
from app.modules.requests.models import RequestStatus, TravelRequest
from app.modules.requests.schemas import BookingSummary, OfferSnapshot


def summary(row, paid=Decimal(0)):
    return BookingSummary(
        id=row.id,
        status=row.status,
        total_amount=f"{row.total_amount:.2f}",
        currency=row.currency,
        paid_amount=f"{paid:.2f}",
        remaining_amount=f"{row.total_amount - paid:.2f}",
    )


def summaries(session, rows, *, with_completion=False):
    amounts = totals(
        session,
        [
            row.id
            for row in rows.values()
            if row.status not in (BookingStatus.PENDING, BookingStatus.REJECTED)
        ],
    )
    result = {
        identity: summary(row, amounts.get(row.id, (Decimal(0), Decimal(0)))[0])
        for identity, row in rows.items()
    }
    if not with_completion:
        return result
    today = (
        business_date(session)
        if any(row.status == BookingStatus.CONFIRMED for row in rows.values())
        else None
    )
    completed = {
        identity
        for identity, row in rows.items()
        if today is not None and eligible(row, amounts.get(row.id, (Decimal(0), Decimal(0))), today)
    }
    return result, completed


def project(session, rows):
    ids = [row.id for row in rows]
    if not ids:
        return []
    amounts = totals(
        session,
        [
            row.id
            for row in rows
            if row.status not in (BookingStatus.PENDING, BookingStatus.REJECTED)
        ],
    )
    request_ids = {
        row.request_id
        for row in rows
        if row.status in (BookingStatus.CONFIRMED, BookingStatus.CANCELLATION_REQUESTED)
    }
    statuses = (
        dict(
            session.execute(
                select(TravelRequest.id, TravelRequest.status).where(
                    TravelRequest.id.in_(request_ids)
                )
            ).all()
        )
        if request_ids
        else {}
    )
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
            paid_amount=f"{amounts.get(row.id, (Decimal(0), Decimal(0)))[0]:.2f}",
            reserved_payment_amount=f"{amounts.get(row.id, (Decimal(0), Decimal(0)))[1]:.2f}",
            remaining_amount=f"{row.total_amount - amounts.get(row.id, (Decimal(0), Decimal(0)))[0]:.2f}",
            available_payment_amount=f"{row.total_amount - sum(amounts.get(row.id, (Decimal(0), Decimal(0)))):.2f}"
            if row.status == BookingStatus.CONFIRMED
            else "0.00",
            refunded_amount="0.00",
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
            tourists=tourists[row.id],
            allowed_actions=allowed_actions(
                row, amounts.get(row.id, (Decimal(0), Decimal(0))), statuses.get(row.request_id)
            ),
        )
        for row in rows
    ]


def allowed_actions(row, money, request_status):
    if row.status == BookingStatus.PENDING:
        return ["confirm", "reject"]
    if request_status != RequestStatus.BOOKED:
        return []
    if row.status == BookingStatus.CONFIRMED:
        return ["request_cancellation"] + (
            ["create_payment"] if row.total_amount > sum(money) else []
        )
    if row.status == BookingStatus.CANCELLATION_REQUESTED:
        return (["confirm_cancellation"] if money[1] == 0 else []) + ["reject_cancellation"]
    return []
