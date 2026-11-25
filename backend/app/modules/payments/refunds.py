from decimal import Decimal

from sqlalchemy import func, select

from app.core.audit import AuditRecord
from app.core.errors import ApiError
from app.core.idempotency import check_payload, find_previous, remember
from app.modules.bookings.models import Booking
from app.modules.payments import refund_views
from app.modules.payments import service as payments
from app.modules.payments.adapter import ProviderError
from app.modules.payments.models import Payment, Refund
from app.modules.payments.refund_schemas import RefundPage
from app.modules.requests import service as requests
from app.modules.requests.models import TravelRequest


def get_visible(session, actor, identity):
    row = session.scalar(
        select(Refund)
        .where(
            Refund.id == identity,
            Refund.payment_id.in_(select(Payment.id).where(payments.visible(actor))),
        )
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise ApiError(404, "not_found", "Возврат не найден")
    return row


def result(session, actor, identity):
    return refund_views.project(session, actor, [get_visible(session, actor, identity)])[0]


def list_refunds(session, actor, query, payment_id=None):
    conditions = [Refund.payment_id.in_(select(Payment.id).where(payments.visible(actor)))]
    if payment_id is not None:
        payments.get_visible(session, actor, payment_id)
        conditions.append(Refund.payment_id == payment_id)
    else:
        if query.payment_id is not None:
            payments.get_visible(session, actor, query.payment_id)
            conditions.append(Refund.payment_id == query.payment_id)
        if query.booking_id is not None:
            if session.get(Booking, query.booking_id) is None:
                raise ApiError(404, "not_found", "Бронь не найдена")
            conditions.append(
                Refund.payment_id.in_(
                    select(Payment.id).where(Payment.booking_id == query.booking_id)
                )
            )
        if query.request_id is not None:
            if session.get(TravelRequest, query.request_id) is None:
                raise ApiError(404, "not_found", "Заявка не найдена")
            conditions.append(
                Refund.payment_id.in_(
                    select(Payment.id).join(Booking).where(Booking.request_id == query.request_id)
                )
            )
        if query.status is not None:
            conditions.append(Refund.status == query.status)
    count = session.scalar(select(func.count()).select_from(Refund).where(*conditions))
    ordering = (
        (Refund.created_at.asc(), Refund.id.asc())
        if query.sort == "created_at"
        else (Refund.created_at.desc(), Refund.id.desc())
    )
    rows = session.scalars(
        select(Refund)
        .where(*conditions)
        .order_by(*ordering)
        .offset(query.offset)
        .limit(query.page_size)
    ).all()
    return RefundPage(
        items=refund_views.project(session, actor, rows),
        page=query.page,
        page_size=query.page_size,
        total=count,
    )


def audit(session, row, request_id, old, new, action, actor_id=None):
    session.add(
        AuditRecord(
            request_id=request_id,
            entity_id=row.id,
            entity_type="refund",
            actor_id=actor_id,
            source="staff" if actor_id else "payment_service",
            action=action,
            changes=[{"field": "refund_status", "old_value": old, "new_value": new}]
            if old != new
            else [],
        )
    )


def expect_capacity(booking):
    if booking.version >= 2_147_483_647:
        raise ApiError(409, "conflict", "Достигнут предел версии брони")


def create(session, actor, identity, body, command, adapter):
    initial = payments.get_visible(session, actor, identity)
    operation = f"POST /api/payments/{identity}/refunds"
    previous = find_previous(session, f"staff:{actor.id}", operation, command)
    initial_booking = session.get(Booking, initial.booking_id)
    requests.locked_request(session, actor, initial_booking.request_id)
    booking = session.scalar(
        select(Booking)
        .where(Booking.id == initial.booking_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    payment = session.scalar(
        select(Payment)
        .where(Payment.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if previous is not None:
        row = get_visible(session, actor, previous.resource_id)
        if previous.resource_type != "refund" or row.payment_id != identity:
            raise ApiError(409, "idempotency_conflict", "Ключ принадлежит другой операции")
        check_payload(previous, command)
        session.commit()
        return synchronize(session, actor, row.id, adapter)
    if not adapter.configured():
        raise ApiError(503, "server_error", "Платёжный сервис не настроен")
    if booking.status != "cancelled" or payment.status != "succeeded":
        raise ApiError(
            409, "invalid_transition", "Возврат доступен после отмены брони по успешному платежу"
        )
    expect_capacity(booking)
    money = refund_views.payment_totals(session, [payment.id]).get(
        payment.id, (Decimal(0), Decimal(0))
    )
    if Decimal(body.amount) > refund_views.available(payment, booking, money):
        raise ApiError(
            409,
            "refund_limit_exceeded",
            "Сумма превышает доступный остаток с учётом ожидающих возвратов",
        )
    row = Refund(payment_id=payment.id, amount=Decimal(body.amount), currency=body.currency)
    session.add(row)
    session.flush()
    booking.version += 1
    audit(session, row, booking.request_id, None, "processing", "refund_created", actor.id)
    remember(
        session, f"staff:{actor.id}", operation, command, resource_type="refund", resource_id=row.id
    )
    identity = row.id
    session.commit()
    return synchronize(session, actor, identity, adapter)


def apply_result(session, identity, data, error):
    initial = session.get(Refund, identity)
    request, booking, payment = payments.locked_system_rows(session, initial.payment_id)
    row = session.scalar(
        select(Refund)
        .where(Refund.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    mismatch = data is not None and (
        data.client_operation_id != row.id
        or str(data.payment_id) != payment.external_operation_id
        or data.amount != f"{row.amount:.2f}"
        or data.currency != row.currency
        or (row.external_operation_id is not None and str(data.id) != row.external_operation_id)
    )
    if row.status != "processing":
        if (
            data is not None
            and (mismatch or (data.status != "processing" and data.status != row.status))
            and not row.provider_conflict
        ):
            row.provider_conflict = True
            audit(session, row, request.id, row.status, row.status, "refund_result_conflict")
        session.commit()
        return
    if mismatch:
        row.pending_reason = "Ответ сервиса не соответствует возврату; требуется сверка"
    elif error is not None:
        row.pending_reason = str(error)
    elif data is not None:
        row.external_operation_id = str(data.id)
        if data.status == "processing":
            row.pending_reason = "Ожидает результата возврата"
        else:
            returned, _ = refund_views.payment_totals(session, [payment.id]).get(
                payment.id, (Decimal(0), Decimal(0))
            )
            if (
                payment.status != "succeeded"
                or booking.status != "cancelled"
                or (data.status == "succeeded" and returned + row.amount > payment.amount)
            ):
                row.pending_reason = (
                    "Результат возврата требует проверки исходной оплаты и отмены брони"
                )
            elif booking.version >= 2_147_483_647:
                row.pending_reason = "Достигнут предел версии брони; требуется сверка"
            else:
                row.status = data.status
                row.pending_reason = None
                row.failure_reason = data.failure_reason if data.status == "failed" else None
                row.succeeded_at = data.succeeded_at if data.status == "succeeded" else None
                booking.version += 1
                audit(session, row, request.id, "processing", row.status, "refund_" + row.status)
    session.commit()


def synchronize_system(session, identity, adapter):
    row = session.get(Refund, identity)
    if row is None or row.status != "processing":
        return
    payment = session.get(Payment, row.payment_id)
    values = (
        row.id,
        row.external_operation_id,
        payment.external_operation_id,
        row.amount,
        row.currency,
    )
    session.commit()
    data, error = None, None
    try:
        data = adapter.fetch_refund(*values)
    except ProviderError as caught:
        error = caught
    apply_result(session, identity, data, error)


def synchronize(session, actor, identity, adapter):
    get_visible(session, actor, identity)
    synchronize_system(session, identity, adapter)
    return result(session, actor, identity)
