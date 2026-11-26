from decimal import Decimal

from sqlalchemy import func, select

from app.modules.auth.models import Role
from app.modules.bookings.models import Booking
from app.modules.payments.models import Payment, Refund
from app.modules.payments.refund_schemas import Refund as RefundDto


def payment_totals(session, ids):
    if not ids:
        return {}
    return {
        identity: (returned or Decimal(0), reserved or Decimal(0))
        for identity, returned, reserved in session.execute(
            select(
                Refund.payment_id,
                func.sum(Refund.amount).filter(Refund.status == "succeeded"),
                func.sum(Refund.amount).filter(Refund.status == "processing"),
            )
            .where(Refund.payment_id.in_(ids))
            .group_by(Refund.payment_id)
        )
    }


def booking_totals(session, ids):
    if not ids:
        return {}
    return {
        identity: (returned or Decimal(0), reserved or Decimal(0))
        for identity, returned, reserved in session.execute(
            select(
                Payment.booking_id,
                func.sum(Refund.amount).filter(Refund.status == "succeeded"),
                func.sum(Refund.amount).filter(Refund.status == "processing"),
            )
            .join(Payment, Payment.id == Refund.payment_id)
            .where(Payment.booking_id.in_(ids))
            .group_by(Payment.booking_id)
        )
    }


def available(payment, booking, money):
    return (
        payment.amount - sum(money)
        if payment.status == "succeeded" and booking.status == "cancelled"
        else Decimal(0)
    )


def project(session, actor, rows):
    if not rows:
        return []
    parents = {
        payment.id: (payment.booking_id, booking.request_id)
        for payment, booking in session.execute(
            select(Payment, Booking)
            .join(Booking, Booking.id == Payment.booking_id)
            .where(Payment.id.in_({row.payment_id for row in rows}))
        )
    }
    return [
        RefundDto(
            id=row.id,
            payment_id=row.payment_id,
            amount=f"{row.amount:.2f}",
            currency=row.currency,
            status=row.status,
            external_operation_id=row.external_operation_id,
            failure_reason=row.failure_reason,
            succeeded_at=row.succeeded_at,
            created_at=row.created_at,
            booking_id=parents[row.payment_id][0],
            request_id=parents[row.payment_id][1],
            pending_reason=row.pending_reason,
            can_open_request=actor.role != Role.ACCOUNTANT,
            allowed_actions=["reconcile"]
            if row.status == "processing" and actor.role != Role.ACCOUNTANT
            else [],
        )
        for row in rows
    ]
