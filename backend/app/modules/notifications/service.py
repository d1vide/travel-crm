from sqlalchemy import case, func, literal, select

from app.core.errors import ApiError
from app.modules.auth.models import Role
from app.modules.bookings.models import Booking
from app.modules.notifications.schemas import Notification, NotificationPage
from app.modules.payments.models import Payment, PaymentNotification
from app.modules.requests.models import TravelRequest


def query_rows(actor):
    visible = literal(True) if actor.role == Role.HEAD else TravelRequest.manager_id == actor.id
    return (
        select(
            PaymentNotification,
            Payment.amount,
            Payment.currency,
            case((visible, Booking.request_id), else_=None),
            visible,
        )
        .join(Payment, Payment.id == PaymentNotification.payment_id)
        .join(Booking, Booking.id == Payment.booking_id)
        .join(TravelRequest, TravelRequest.id == Booking.request_id)
    )


def project(result):
    row, amount, currency, request_id, visible = result
    return Notification(
        id=row.id,
        recipient_id=row.recipient_id,
        payment_id=row.payment_id,
        type=row.type,
        read_at=row.read_at,
        created_at=row.created_at,
        request_id=request_id,
        amount=f"{amount:.2f}",
        currency=currency,
        can_open_request=visible,
    )


def list_notifications(session, actor, query):
    condition = PaymentNotification.recipient_id == actor.id
    total, unread = session.execute(
        select(
            func.count(PaymentNotification.id),
            func.count(PaymentNotification.id).filter(PaymentNotification.read_at.is_(None)),
        ).where(condition)
    ).one()
    rows = session.execute(
        query_rows(actor)
        .where(condition, *([PaymentNotification.read_at.is_(None)] if query.unread_only else []))
        .order_by(PaymentNotification.created_at.desc(), PaymentNotification.id.desc())
        .offset(query.offset)
        .limit(query.page_size)
    ).all()
    return NotificationPage(
        items=[project(row) for row in rows],
        page=query.page,
        page_size=query.page_size,
        total=unread if query.unread_only else total,
        unread_count=unread,
    )


def mark_read(session, actor, identity):
    row = session.scalar(
        select(PaymentNotification)
        .where(PaymentNotification.id == identity, PaymentNotification.recipient_id == actor.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise ApiError(404, "not_found", "Уведомление не найдено")
    if row.read_at is None:
        row.read_at = session.scalar(select(func.clock_timestamp()))
    session.flush()
    result = project(
        session.execute(
            query_rows(actor).where(
                PaymentNotification.id == identity, PaymentNotification.recipient_id == actor.id
            )
        ).one()
    )
    session.commit()
    return result
