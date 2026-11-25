from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy import and_, func, or_, select

from app.core.audit import AuditRecord
from app.core.errors import ApiError
from app.core.idempotency import check_payload, find_previous, remember
from app.modules.auth.models import Role, User
from app.modules.bookings import service as bookings
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.clients.models import Client
from app.modules.payments import views
from app.modules.payments.adapter import ProviderError
from app.modules.payments.models import Payment, PaymentNotification
from app.modules.payments.schemas import PaymentPage
from app.modules.requests import service as requests
from app.modules.requests.access import request_is_visible
from app.modules.requests.models import TravelRequest


def visible(actor):
    return (
        True
        if actor.role in (Role.HEAD, Role.ACCOUNTANT)
        else Payment.booking_id.in_(
            select(Booking.id).where(request_is_visible(Booking.request_id, actor))
        )
    )


def get_visible(session, actor, identity):
    row = session.scalar(
        select(Payment)
        .where(Payment.id == identity, visible(actor))
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise ApiError(404, "not_found", "Платёж не найден")
    return row


def result(session, actor, identity):
    return views.project(session, actor, [get_visible(session, actor, identity)])[0]


def list_payments(session, actor, query, booking_id=None):
    conditions = [visible(actor)]
    if booking_id is not None:
        bookings.get_visible(session, actor, booking_id)
        conditions.append(Payment.booking_id == booking_id)
    else:
        if query.request_id is not None:
            if (
                session.scalar(select(TravelRequest.id).where(TravelRequest.id == query.request_id))
                is None
            ):
                raise ApiError(404, "not_found", "Заявка не найдена")
            conditions.append(
                Payment.booking_id.in_(
                    select(Booking.id).where(Booking.request_id == query.request_id)
                )
            )
        if query.booking_id is not None:
            if session.get(Booking, query.booking_id) is None:
                raise ApiError(404, "not_found", "Бронь не найдена")
            conditions.append(Payment.booking_id == query.booking_id)
        if query.status is not None:
            conditions.append(Payment.status == query.status)
    total = session.scalar(select(func.count()).select_from(Payment).where(*conditions))
    order = (
        (Payment.created_at.asc(), Payment.id.asc())
        if query.sort == "created_at"
        else (Payment.created_at.desc(), Payment.id.desc())
    )
    rows = session.scalars(
        select(Payment)
        .where(*conditions)
        .order_by(*order)
        .offset(query.offset)
        .limit(query.page_size)
    ).all()
    return PaymentPage(
        items=views.project(session, actor, rows),
        page=query.page,
        page_size=query.page_size,
        total=total,
    )


def create_payment(session, actor, identity, body, command, adapter):
    initial = bookings.get_visible(session, actor, identity)
    operation = f"POST /api/bookings/{identity}/payments"
    previous = find_previous(session, f"staff:{actor.id}", operation, command)
    requests.locked_request(session, actor, initial.request_id)
    booking = session.scalar(
        select(Booking)
        .where(Booking.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if previous is not None:
        if previous.resource_type != "payment":
            raise ApiError(409, "idempotency_conflict", "Ключ принадлежит другой операции")
        row = get_visible(session, actor, previous.resource_id)
        check_payload(previous, command)
        session.commit()
        # An explicit replay can recover a provider create whose response was lost.
        return synchronize(session, actor, row.id, adapter)
    if not adapter.configured():
        raise ApiError(503, "server_error", "Платёжный сервис не настроен")
    if booking.version != body.version:
        raise ApiError(409, "version_conflict", "Бронь уже изменена. Обновите данные")
    if booking.version >= 2_147_483_647:
        raise ApiError(409, "conflict", "Достигнут предел версии брони")
    if booking.status != BookingStatus.CONFIRMED:
        raise ApiError(409, "invalid_transition", "Оплата доступна только для подтверждённой брони")
    paid, reserved = views.totals(session, [identity]).get(identity, (Decimal(0), Decimal(0)))
    if Decimal(body.amount) > booking.total_amount - paid - reserved:
        raise ApiError(
            409,
            "payment_limit_exceeded",
            "Сумма превышает доступный остаток с учётом ожидающих платежей",
        )
    row = Payment(booking_id=identity, amount=Decimal(body.amount), currency=body.currency)
    session.add(row)
    session.flush()
    booking.version += 1
    audit(session, row, booking.request_id, None, "pending", "payment_created", "staff", actor.id)
    remember(
        session,
        f"staff:{actor.id}",
        operation,
        command,
        resource_type="payment",
        resource_id=row.id,
    )
    payment_id = row.id
    session.commit()
    return synchronize(session, actor, payment_id, adapter)


def audit(session, row, request_id, old, new, action, source="payment_service", actor_id=None):
    session.add(
        AuditRecord(
            request_id=request_id,
            entity_id=row.id,
            entity_type="payment",
            actor_id=actor_id,
            source=source,
            action=action,
            changes=[{"field": "payment_status", "old_value": old, "new_value": new}]
            if old != new
            else [],
        )
    )


def locked_system_rows(session, identity):
    payment = session.get(Payment, identity)
    initial_booking = session.get(Booking, payment.booking_id)
    initial_request = session.get(TravelRequest, initial_booking.request_id)
    session.scalar(select(Client).where(Client.id == initial_request.client_id).with_for_update())
    request = session.scalar(
        select(TravelRequest)
        .where(TravelRequest.id == initial_request.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    booking = session.scalar(
        select(Booking)
        .where(Booking.id == payment.booking_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    row = session.scalar(
        select(Payment)
        .where(Payment.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return request, booking, row


def apply_result(session, identity, data, error, adapter):
    request, booking, row = locked_system_rows(session, identity)
    if data is not None and (
        data.client_operation_id != row.id
        or data.amount != f"{row.amount:.2f}"
        or data.currency != row.currency
    ):
        if row.status == "pending":
            row.pending_reason = "Ответ сервиса не соответствует платежу; требуется сверка"
        elif not row.provider_conflict:
            row.provider_conflict = True
            audit(session, row, request.id, row.status, row.status, "payment_result_conflict")
        session.commit()
        return
    if row.status != "pending":
        if (
            data is not None
            and (
                (data.status != "pending" and data.status != row.status)
                or str(data.id) != row.external_operation_id
            )
            and not row.provider_conflict
        ):
            row.provider_conflict = True
            audit(session, row, request.id, row.status, row.status, "payment_result_conflict")
        session.commit()
        return
    if error is not None:
        row.pending_reason = str(error)
        session.commit()
        return
    if (row.external_operation_id is not None and row.external_operation_id != str(data.id)) or (
        row.payment_url is not None
        and urlsplit(row.payment_url).path != urlsplit(adapter.url(data)).path
    ):
        row.pending_reason = "Ответ сервиса не соответствует платежу; требуется сверка"
        session.commit()
        return
    row.external_operation_id = str(data.id)
    row.payment_url = adapter.url(data)
    if data.status == "pending":
        row.pending_reason = "Ожидает тестовой оплаты"
        session.commit()
        return
    paid, _reserved = views.totals(session, [booking.id]).get(booking.id, (Decimal(0), Decimal(0)))
    if data.status == "succeeded" and paid + row.amount > booking.total_amount:
        row.pending_reason = "Сумма результата превышает стоимость брони; требуется сверка"
        session.commit()
        return
    if booking.version >= 2_147_483_647:
        row.pending_reason = "Достигнут предел версии брони; требуется сверка"
        session.commit()
        return
    row.status = data.status
    row.pending_reason = None
    row.failure_reason = data.failure_reason if data.status == "failed" else None
    row.succeeded_at = data.succeeded_at if data.status == "succeeded" else None
    booking.version += 1
    audit(session, row, request.id, "pending", row.status, "payment_" + row.status)
    if row.status == "succeeded":
        recipients = set(
            session.scalars(
                select(User.id).where(
                    or_(
                        User.id == request.manager_id,
                        and_(User.role == Role.HEAD, User.is_active.is_(True)),
                    )
                )
            )
        )
        for user_id in recipients:
            session.add(PaymentNotification(recipient_id=user_id, payment_id=row.id))
    session.commit()


def synchronize(session, actor, identity, adapter):
    row = get_visible(session, actor, identity)
    if row.status != "pending":
        return result(session, actor, identity)
    synchronize_system(session, identity, adapter)
    return result(session, actor, identity)


def synchronize_system(session, identity, adapter):
    row = session.get(Payment, identity)
    if row is None or row.status != "pending":
        return
    values = (row.id, row.external_operation_id, row.amount, row.currency)
    session.commit()
    data, error = None, None
    try:
        data = adapter.fetch(*values)
    except ProviderError as caught:
        error = caught
    apply_result(session, identity, data, error, adapter)
