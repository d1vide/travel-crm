from decimal import Decimal

from sqlalchemy import func, select

from app.modules.auth.models import Role
from app.modules.bookings.models import Booking
from app.modules.payments.models import Payment
from app.modules.payments.schemas import Payment as PaymentDto


def totals(session, ids):
    if not ids:
        return {}
    return {
        identity: (paid or Decimal(0), reserved or Decimal(0))
        for identity, paid, reserved in session.execute(
            select(
                Payment.booking_id,
                func.sum(Payment.amount).filter(Payment.status == "succeeded"),
                func.sum(Payment.amount).filter(Payment.status == "pending"),
            )
            .where(Payment.booking_id.in_(ids))
            .group_by(Payment.booking_id)
        )
    }


def project(session, actor, rows):
    if not rows:
        return []
    bookings = {
        row.id: row
        for row in session.scalars(
            select(Booking).where(Booking.id.in_({row.booking_id for row in rows}))
        )
    }
    return [
        PaymentDto(
            id=row.id,
            booking_id=row.booking_id,
            amount=f"{row.amount:.2f}",
            currency=row.currency,
            status=row.status,
            external_operation_id=row.external_operation_id,
            payment_url=row.payment_url,
            failure_reason=row.failure_reason,
            succeeded_at=row.succeeded_at,
            created_at=row.created_at,
            request_id=bookings[row.booking_id].request_id,
            booking_status=bookings[row.booking_id].status,
            pending_reason=row.pending_reason,
            refunded_amount="0.00",
            reserved_refund_amount="0.00",
            available_refund_amount="0.00",
            can_open_request=actor.role != Role.ACCOUNTANT,
            allowed_actions=["reconcile"]
            if row.status == "pending" and actor.role != Role.ACCOUNTANT
            else [],
        )
        for row in rows
    ]
