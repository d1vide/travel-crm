from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.audit import AuditRecord, record_request_change
from app.core.errors import ApiError
from app.core.idempotency import check_payload, find_previous, remember
from app.modules.bookings import views
from app.modules.bookings.access import ensure_no_active
from app.modules.bookings.models import Booking, BookingStatus, BookingTourist
from app.modules.bookings.schemas import BookingPage
from app.modules.requests import service as requests
from app.modules.requests.access import request_is_visible
from app.modules.requests.models import RequestStatus
from app.modules.requests.schemas import OfferSnapshot
from app.modules.tourists.models import Tourist
from app.modules.tourists.schemas import TouristFields
from app.modules.tours.selection_models import SelectionItem
from app.modules.tours.selection_views import latest_ids


def invalid():
    raise ApiError(409, "invalid_transition", "Бронь недоступна для этой операции")


def get_visible(session, actor, identity):
    row = session.scalar(
        select(Booking).where(Booking.id == identity, request_is_visible(Booking.request_id, actor))
    )
    if row is None:
        raise ApiError(404, "not_found", "Бронь не найдена")
    return row


def get_booking(session, actor, identity):
    return views.project(session, [get_visible(session, actor, identity)])[0]


def list_bookings(session, actor, identity, query):
    requests.get_visible(session, actor, identity)
    condition = (Booking.request_id == identity) & request_is_visible(Booking.request_id, actor)
    total = session.scalar(select(func.count()).select_from(Booking).where(condition))
    rows = session.scalars(
        select(Booking)
        .where(condition)
        .order_by(Booking.created_at.desc(), Booking.id.desc())
        .offset(query.offset)
        .limit(query.page_size)
    ).all()
    return BookingPage(
        items=views.project(session, rows), page=query.page, page_size=query.page_size, total=total
    )


def selected_item(session, request):
    if request.status != RequestStatus.OFFER_PREPARED or request.selected_selection_item_id is None:
        invalid()
    item = session.get(SelectionItem, request.selected_selection_item_id)
    if (
        item is None
        or item.request_id != request.id
        or latest_ids(session, [request.id]).get(request.id) != item.selection_id
    ):
        invalid()
    return item


def checked_tourists(session, request, offer):
    rows = session.scalars(
        select(Tourist)
        .where(Tourist.request_id == request.id, Tourist.removed_at.is_(None))
        .order_by(Tourist.position, Tourist.id)
    ).all()
    if len(rows) != request.tourist_count or len(rows) != offer.tourist_count:
        raise ApiError(
            409, "invalid_transition", "Нужен полный список туристов, совпадающий с заявкой и туром"
        )
    snapshots = []
    for row in rows:
        values = {field: getattr(row, field) for field in TouristFields.model_fields}
        for field in ("birth_date", "document_expires_on"):
            values[field] = values[field].isoformat() if values[field] is not None else None
        try:
            data = TouristFields.model_validate(values).model_dump(mode="json")
        except ValidationError:
            raise ApiError(
                409, "invalid_transition", "Исправьте данные туристов перед бронированием"
            ) from None
        snapshots.append((row, data))
    return snapshots


def audit(session, row, actor, old_value, new_value, action):
    session.add(
        AuditRecord(
            request_id=row.request_id,
            entity_id=row.id,
            entity_type="booking",
            actor_id=actor.id,
            source="staff",
            action=action,
            changes=[
                {"field": "booking_status", "old_value": old_value, "new_value": str(new_value)}
            ],
        )
    )


def replay(session, actor, previous, command, identity):
    if previous.resource_type != "booking":
        raise ApiError(409, "idempotency_conflict", "Ключ принадлежит другой операции")
    row = get_visible(session, actor, previous.resource_id)
    if row.request_id != identity:
        raise ApiError(409, "idempotency_conflict", "Ключ принадлежит другой операции")
    check_payload(previous, command)
    result = views.project(session, [row])[0]
    session.commit()
    return result


def finish(session, actor, row, operation, command):
    session.flush()
    remember(
        session,
        f"staff:{actor.id}",
        operation,
        command,
        resource_type="booking",
        resource_id=row.id,
    )
    result = views.project(session, [row])[0]
    session.commit()
    return result


def create_booking(session, actor, identity, body, command):
    requests.get_visible(session, actor, identity)
    operation = f"POST /api/requests/{identity}/bookings"
    previous = find_previous(session, f"staff:{actor.id}", operation, command)
    request = requests.locked_request(session, actor, identity)
    if previous is not None:
        return replay(session, actor, previous, command, identity)
    requests.expect_version(request, body.version)
    ensure_no_active(session, identity)
    item = selected_item(session, request)
    snapshot = OfferSnapshot.model_validate(item.offer_snapshot)
    checked_tourists(session, request, snapshot)
    row = Booking(
        request_id=identity,
        selection_item_id=item.id,
        offer_snapshot=snapshot.model_dump(mode="json"),
        total_amount=Decimal(snapshot.price),
    )
    session.add(row)
    session.flush()
    request.version += 1
    audit(session, row, actor, None, BookingStatus.PENDING, "booking_created")
    return finish(session, actor, row, operation, command)


def act(session, actor, identity, body, command, action):
    initial = get_visible(session, actor, identity)
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
        return replay(session, actor, previous, command, request.id)
    if row.version != body.version:
        raise ApiError(409, "version_conflict", "Бронь уже изменена. Обновите данные")
    if row.version >= 2_147_483_647:
        raise ApiError(409, "conflict", "Достигнут предел версии брони")
    requests.expect_version(request, request.version)
    if row.status != BookingStatus.PENDING or request.status != RequestStatus.OFFER_PREPARED:
        invalid()
    if request.selected_selection_item_id != row.selection_item_id:
        invalid()
    if action == "confirm":
        offer = OfferSnapshot.model_validate(row.offer_snapshot)
        tourists = checked_tourists(session, request, offer)
        for position, (tourist, data) in enumerate(tourists):
            session.add(
                BookingTourist(
                    booking_id=row.id,
                    request_id=request.id,
                    tourist_id=tourist.id,
                    position=position,
                    tourist_snapshot=data,
                )
            )
        row.supplier_booking_number = body.supplier_booking_number
        row.confirmed_at = session.scalar(select(func.clock_timestamp()))
        row.status = BookingStatus.CONFIRMED
        record_request_change(
            session,
            request,
            actor,
            "request_status",
            request.status,
            RequestStatus.BOOKED,
            "booking_confirmed",
        )
        request.status = RequestStatus.BOOKED
    else:
        row.status = BookingStatus.REJECTED
        row.rejection_reason = body.reason
        request.selected_selection_item_id = None
    audit(session, row, actor, BookingStatus.PENDING, row.status, f"booking_{row.status}")
    row.version += 1
    request.version += 1
    return finish(session, actor, row, operation, command)
