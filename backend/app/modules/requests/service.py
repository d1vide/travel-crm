from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.core.audit import AuditRecord as AuditRow
from app.core.audit import record_request_change
from app.core.errors import ApiError
from app.core.idempotency import check_payload, find_previous, remember
from app.modules.auth.directory import active_assignee, user_briefs
from app.modules.auth.models import Role
from app.modules.bookings import views as booking_views
from app.modules.bookings.access import active_bookings, ensure_no_active, pending_request_ids
from app.modules.clients import service as clients
from app.modules.requests.models import RequestStatus as Status
from app.modules.requests.models import TravelRequest
from app.modules.requests.schemas import AuditRecord, AuditRecordPage, Request, RequestPage
from app.modules.tourists import views as tourist_views
from app.modules.tours import selection_views


def visible_requests(actor):
    return True if actor.role == Role.HEAD else TravelRequest.manager_id == actor.id


def get_visible(session, actor, identity, *, lock=False):
    query = select(TravelRequest).where(TravelRequest.id == identity, visible_requests(actor))
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = session.scalar(query)
    if row is None:
        raise ApiError(404, "not_found", "Заявка не найдена")
    return row


def locked_request(session, actor, identity):
    initial = get_visible(session, actor, identity)
    # Creation and reassignment lock the same parent before the request row.
    clients.get_visible(session, actor, initial.client_id, lock=True)
    return get_visible(session, actor, identity, lock=True)


def allowed_actions(
    row,
    actor,
    latest_selection_id=None,
    has_booking=False,
    can_book=False,
    can_complete=False,
    has_pending=False,
):
    actions = ["reassign"] if actor.role == Role.HEAD else []
    if not has_booking and row.status in (Status.NEW, Status.IN_PROGRESS):
        actions += ["update", "cancel"]
    if not has_booking and row.status == Status.NEW:
        actions.append("start_work")
    if not has_booking and not has_pending and row.status == Status.CANCELLED:
        actions.append("resume")
    if not has_booking and row.status in (Status.IN_PROGRESS, Status.OFFER_PREPARED):
        actions.append("prepare_selection")
    if tourist_views.is_editable(row, has_booking):
        actions += ["issue_tourist_link", "edit_tourists"]
    if not has_booking and row.status == Status.OFFER_PREPARED:
        actions += ["return_to_work", "cancel"]
        if latest_selection_id is not None:
            actions.append("select_tour")
    if can_book:
        actions.append("create_booking")
    if row.status == Status.BOOKED and can_complete:
        actions.append("complete")
    return actions


def project(session, actor, rows):
    client_map = clients.request_client_briefs(session, {row.client_id for row in rows})
    manager_map = user_briefs(session, {row.manager_id for row in rows})
    details = selection_views.request_details(session, rows)
    bookings = active_bookings(session, rows)
    booking_summaries, can_complete = booking_views.summaries(
        session, bookings, with_completion=True
    )
    tourists = tourist_views.request_details(session, rows, bookings)
    pending = pending_request_ids(
        session, [row.id for row in rows if row.status == Status.CANCELLED]
    )
    return [
        Request(
            id=row.id,
            client_id=row.client_id,
            manager_id=row.manager_id,
            destination=row.destination,
            starts_on=row.starts_on,
            ends_on=row.ends_on,
            tourist_count=row.tourist_count,
            budget=f"{row.budget:.2f}",
            wishes=row.wishes,
            status=row.status,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
            completed_at=row.completed_at,
            cancelled_at=row.cancelled_at,
            cancellation_reason=row.cancellation_reason,
            client=client_map[row.client_id],
            manager=manager_map[row.manager_id],
            selected_selection_item_id=row.selected_selection_item_id,
            selected_selection_id=details[row.id]["selected_selection_id"],
            selected_offer=details[row.id]["selected_offer"],
            active_booking=booking_summaries.get(row.id),
            tourists_received=tourists[row.id]["tourists_received"],
            tourist_form_editable=tourists[row.id]["tourist_form_editable"],
            tourist_link=tourists[row.id]["tourist_link"],
            allowed_actions=allowed_actions(
                row,
                actor,
                details[row.id]["latest_selection_id"],
                row.id in bookings,
                can_complete=row.id in can_complete,
                has_pending=row.id in pending,
                can_book=(
                    row.status == Status.OFFER_PREPARED
                    and row.id not in bookings
                    and details[row.id]["selected_offer"] is not None
                    and details[row.id]["selected_selection_id"]
                    == details[row.id]["latest_selection_id"]
                    and tourists[row.id]["tourists_received"] == row.tourist_count
                    and details[row.id]["selected_offer"].tourist_count == row.tourist_count
                ),
            ),
        )
        for row in rows
    ]


def card(session, actor, row):
    return project(session, actor, [row])[0]


def list_requests(session, actor, query):
    if actor.role == Role.MANAGER and query.manager_id not in (None, actor.id):
        raise ApiError(403, "forbidden", "Нельзя выбирать чужого ответственного")
    conditions = [visible_requests(actor)]
    if query.client_id is not None:
        clients.get_visible(session, actor, query.client_id)
        conditions.append(TravelRequest.client_id == query.client_id)
    if query.manager_id is not None:
        conditions.append(TravelRequest.manager_id == query.manager_id)
    if query.status is not None:
        conditions.append(TravelRequest.status == query.status)
    ordering = {
        "-created_at": (TravelRequest.created_at.desc(), TravelRequest.id.desc()),
        "created_at": (TravelRequest.created_at.asc(), TravelRequest.id.asc()),
        "starts_on": (TravelRequest.starts_on.asc(), TravelRequest.id.asc()),
    }[query.sort]
    total = session.scalar(select(func.count()).select_from(TravelRequest).where(*conditions))
    rows = session.scalars(
        select(TravelRequest)
        .where(*conditions)
        .order_by(*ordering)
        .offset(query.offset)
        .limit(query.page_size)
    ).all()
    return RequestPage(
        items=project(session, actor, rows), page=query.page, page_size=query.page_size, total=total
    )


def assign_fields(row, body):
    for field in ("destination", "starts_on", "ends_on", "tourist_count", "wishes"):
        setattr(row, field, getattr(body, field))
    row.budget = Decimal(body.budget)


def replay(session, actor, previous, command):
    if previous.resource_type != "request":
        raise ApiError(409, "idempotency_conflict", "Ключ принадлежит другой операции")
    row = locked_request(session, actor, previous.resource_id)
    check_payload(previous, command)
    result = card(session, actor, row)
    session.commit()
    return result


def finish(session, actor, row, operation, command):
    session.flush()
    remember(
        session,
        f"staff:{actor.id}",
        operation,
        command,
        resource_type="request",
        resource_id=row.id,
    )
    result = card(session, actor, row)
    session.commit()
    return result


def create_request(session, actor, body, command):
    operation = "POST /api/requests"
    previous = find_previous(session, f"staff:{actor.id}", operation, command)
    if previous is not None:
        return replay(session, actor, previous, command)
    manager_id = body.manager_id or actor.id
    if actor.role == Role.MANAGER and manager_id != actor.id:
        raise ApiError(403, "forbidden", "Менеджер может назначить только себя")
    clients.get_visible(session, actor, body.client_id, lock=True)
    active_assignee(session, manager_id)
    row = TravelRequest(client_id=body.client_id, manager_id=manager_id)
    assign_fields(row, body)
    session.add(row)
    session.flush()
    record_request_change(session, row, actor, "request_status", None, row.status, "created")
    return finish(session, actor, row, operation, command)


def mutate_request(session, actor, identity: UUID, body, command, action):
    get_visible(session, actor, identity)
    suffix = (
        "" if action == "update" else "/assignee" if action == "assign" else f"/actions/{action}"
    )
    method = "PUT" if action == "update" else "PATCH" if action == "assign" else "POST"
    operation = f"{method} /api/requests/{identity}{suffix}"
    previous = find_previous(session, f"staff:{actor.id}", operation, command)
    if previous is not None:
        return replay(session, actor, previous, command)
    row = locked_request(session, actor, identity)
    expect_version(row, body.version)
    if action != "assign":
        ensure_no_active(session, row.id)
    if action == "assign":
        if actor.role != Role.HEAD:
            raise ApiError(403, "forbidden", "Смена ответственного доступна руководителю")
        active_assignee(session, body.manager_id)
        if row.manager_id != body.manager_id:
            record_request_change(
                session,
                row,
                actor,
                "manager_id",
                row.manager_id,
                body.manager_id,
                "assignee_changed",
            )
            row.manager_id = body.manager_id
            row.version += 1
    elif action == "update":
        if row.status not in (Status.NEW, Status.IN_PROGRESS):
            invalid_transition()
        assign_fields(row, body)
        row.version += 1
    else:
        transitions = {
            "start-work": ({Status.NEW}, Status.IN_PROGRESS),
            "cancel": ({Status.NEW, Status.IN_PROGRESS, Status.OFFER_PREPARED}, Status.CANCELLED),
            "resume": ({Status.CANCELLED}, Status.IN_PROGRESS),
            "return-to-work": ({Status.OFFER_PREPARED}, Status.IN_PROGRESS),
        }
        allowed, target = transitions[action]
        if row.status not in allowed:
            invalid_transition()
        if action == "resume" and pending_request_ids(session, [row.id]):
            raise ApiError(
                409, "invalid_transition", "Дождитесь окончательного результата платежей"
            )
        if action in ("cancel", "resume", "return-to-work"):
            from app.modules.tours.selection_service import invalidate_request

            invalidate_request(session, row.id)
            row.selected_selection_item_id = None
        record_request_change(session, row, actor, "request_status", row.status, target, action)
        row.status = target
        row.version += 1
        if action == "cancel":
            row.cancellation_reason = body.reason
            row.cancelled_at = session.scalar(select(func.clock_timestamp()))
        if action == "resume":
            row.cancellation_reason = None
            row.cancelled_at = None
    return finish(session, actor, row, operation, command)


def expect_version(row, version):
    if row.version != version:
        raise ApiError(409, "version_conflict", "Заявка уже изменена. Обновите данные")
    if row.version >= 2_147_483_647:
        raise ApiError(409, "conflict", "Достигнут предел версии заявки")


def invalid_transition():
    raise ApiError(409, "invalid_transition", "Действие недоступно в текущем состоянии заявки")


def list_history(session, actor, identity, query):
    get_visible(session, actor, identity)
    condition = AuditRow.request_id == identity
    total = session.scalar(select(func.count()).select_from(AuditRow).where(condition))
    rows = session.scalars(
        select(AuditRow)
        .where(condition)
        .order_by(AuditRow.created_at.desc(), AuditRow.id.desc())
        .offset(query.offset)
        .limit(query.page_size)
    ).all()
    actors = user_briefs(session, {row.actor_id for row in rows if row.actor_id is not None})
    return AuditRecordPage(
        items=[
            AuditRecord(
                id=row.id,
                request_id=row.request_id,
                entity_id=row.entity_id,
                entity_type=row.entity_type,
                actor=actors.get(row.actor_id),
                source=row.source,
                action=row.action,
                changes=row.changes,
                created_at=row.created_at,
            )
            for row in rows
        ],
        page=query.page,
        page_size=query.page_size,
        total=total,
    )
