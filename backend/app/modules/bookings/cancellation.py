from decimal import Decimal

from sqlalchemy import func, select

from app.core.audit import record_request_change
from app.core.errors import ApiError
from app.core.idempotency import find_previous
from app.modules.bookings import service
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.payments.views import totals
from app.modules.requests import service as requests
from app.modules.requests.models import RequestStatus
from app.modules.tours.selection_service import invalidate_request


def act(session, actor, identity, body, command, action):
    initial = service.get_visible(session, actor, identity)
    operation = f"POST /api/bookings/{identity}/actions/{action}"
    previous = find_previous(session, f"staff:{actor.id}", operation, command)
    request = requests.locked_request(session, actor, initial.request_id)
    row = session.scalar(
        select(Booking)
        .where(Booking.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if previous is not None:
        return service.replay(session, actor, previous, command, request.id)
    if row.version != body.version:
        raise ApiError(409, "version_conflict", "Бронь уже изменена. Обновите данные")
    if row.version >= 2_147_483_647:
        raise ApiError(409, "conflict", "Достигнут предел версии брони")
    requests.expect_version(request, request.version)
    expected = (
        BookingStatus.CONFIRMED
        if action == "request-cancellation"
        else BookingStatus.CANCELLATION_REQUESTED
    )
    if (
        row.status != expected
        or request.status != RequestStatus.BOOKED
        or request.selected_selection_item_id != row.selection_item_id
    ):
        service.invalid()
    old = row.status
    if action == "request-cancellation":
        row.status = BookingStatus.CANCELLATION_REQUESTED
        row.cancellation_reason = body.reason
        row.cancellation_response = None
        audit_action = "booking_cancellation_requested"
    elif action == "reject-cancellation":
        row.status = BookingStatus.CONFIRMED
        row.cancellation_response = body.reason
        audit_action = "booking_cancellation_rejected"
    else:
        paid, reserved = totals(session, [row.id]).get(row.id, (Decimal(0), Decimal(0)))
        if reserved:
            raise ApiError(
                409,
                "invalid_transition",
                "Дождитесь окончательного результата ожидающих платежей перед отменой брони",
            )
        row.status = BookingStatus.CANCELLED
        row.cancellation_response = body.supplier_response
        row.cancelled_at = session.scalar(select(func.clock_timestamp()))
        target = RequestStatus.CANCELLED if paid else RequestStatus.IN_PROGRESS
        record_request_change(
            session, request, actor, "request_status", request.status, target, "booking_cancelled"
        )
        request.status = target
        request.selected_selection_item_id = None
        request.cancelled_at = row.cancelled_at if paid else None
        request.cancellation_reason = row.cancellation_reason if paid else None
        invalidate_request(session, request.id)
        audit_action = "booking_cancelled"
    service.audit(session, row, actor, old, row.status, audit_action)
    row.version += 1
    request.version += 1
    return service.finish(session, actor, row, operation, command)
