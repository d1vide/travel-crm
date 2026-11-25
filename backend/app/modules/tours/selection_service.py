from datetime import timedelta

from sqlalchemy import func, or_, select, update

from app.core.audit import record_request_change
from app.core.errors import ApiError
from app.core.idempotency import check_payload, find_previous, remember
from app.core.link_schemas import PublicLink as PublicLinkDto
from app.core.public_links import PublicLink, new_token, token_hash
from app.modules.bookings.access import ensure_no_active
from app.modules.requests import service as requests
from app.modules.requests.access import request_is_visible
from app.modules.requests.models import RequestStatus as Status
from app.modules.tours import selection_views
from app.modules.tours import service as catalogue
from app.modules.tours.selection_models import Selection, SelectionItem
from app.modules.tours.selection_schemas import PublicSelection, PublicSelectionItem, SelectionPage


def get_visible(session, actor, identity):
    row = session.get(Selection, identity)
    if row is None:
        raise ApiError(404, "not_found", "Подборка не найдена")
    try:
        requests.get_visible(session, actor, row.request_id)
    except ApiError as error:
        if error.status == 404:
            raise ApiError(404, "not_found", "Подборка не найдена") from None
        raise
    return row


def get_selection(session, actor, identity):
    return selection_views.project(session, [get_visible(session, actor, identity)])[0]


def list_selections(session, actor, request_id, query):
    requests.get_visible(session, actor, request_id)
    condition = (Selection.request_id == request_id) & request_is_visible(
        Selection.request_id, actor
    )
    total = session.scalar(select(func.count()).select_from(Selection).where(condition))
    rows = session.scalars(
        select(Selection)
        .where(condition)
        .order_by(Selection.created_at.desc(), Selection.id.desc())
        .offset(query.offset)
        .limit(query.page_size)
    ).all()
    return SelectionPage(
        items=selection_views.project(session, rows),
        page=query.page,
        page_size=query.page_size,
        total=total,
    )


def invalidate_request(session, request_id, *, include_tourists=True):
    conditions = [
        PublicLink.selection_id.in_(select(Selection.id).where(Selection.request_id == request_id))
    ]
    if include_tourists:
        conditions.append(PublicLink.request_id == request_id)
    session.execute(
        update(PublicLink)
        .where(or_(*conditions), PublicLink.revoked_at.is_(None))
        .values(revoked_at=func.clock_timestamp())
        .execution_options(synchronize_session=False)
    )


def create_selection(session, actor, request_id, body, command):
    requests.get_visible(session, actor, request_id)
    operation = f"POST /api/requests/{request_id}/selections"
    scope = f"staff:{actor.id}"
    previous = find_previous(session, scope, operation, command)
    request = requests.locked_request(session, actor, request_id)
    if previous is not None:
        row = get_visible(session, actor, previous.resource_id)
        if previous.resource_type != "selection" or row.request_id != request_id:
            raise ApiError(409, "idempotency_conflict", "Ключ принадлежит другой операции")
        check_payload(previous, command)
        result = selection_views.project(session, [row])[0]
        session.commit()
        return result
    requests.expect_version(request, body.version)
    ensure_no_active(session, request.id)
    if request.status not in (Status.IN_PROGRESS, Status.OFFER_PREPARED):
        requests.invalid_transition()
    snapshots = catalogue.snapshots_for_selection(session, body.tour_offer_ids)
    invalidate_request(session, request_id, include_tourists=False)
    row = Selection(request_id=request_id, created_by_id=actor.id)
    session.add(row)
    session.flush()
    for position, identity in enumerate(body.tour_offer_ids):
        session.add(
            SelectionItem(
                selection_id=row.id,
                request_id=request_id,
                tour_offer_id=identity,
                position=position,
                offer_snapshot=snapshots[identity],
            )
        )
    if request.status != Status.OFFER_PREPARED:
        record_request_change(
            session,
            request,
            actor,
            "request_status",
            request.status,
            Status.OFFER_PREPARED,
            "selection_prepared",
        )
    request.status = Status.OFFER_PREPARED
    request.selected_selection_item_id = None
    request.version += 1
    session.flush()
    remember(session, scope, operation, command, resource_type="selection", resource_id=row.id)
    result = selection_views.project(session, [row])[0]
    session.commit()
    return result


def current_selection(session, request, identity):
    ensure_no_active(session, request.id)
    if (
        request.status != Status.OFFER_PREPARED
        or selection_views.latest_ids(session, [request.id]).get(request.id) != identity
    ):
        requests.invalid_transition()


def select_tour(session, actor, request_id, body, command):
    requests.get_visible(session, actor, request_id)
    operation = f"PUT /api/requests/{request_id}/selected-tour"
    scope = f"staff:{actor.id}"
    previous = find_previous(session, scope, operation, command)
    request = requests.locked_request(session, actor, request_id)
    if previous is not None:
        if previous.resource_type != "request" or previous.resource_id != request_id:
            raise ApiError(409, "idempotency_conflict", "Ключ принадлежит другой операции")
        check_payload(previous, command)
        result = requests.card(session, actor, request)
        session.commit()
        return result
    requests.expect_version(request, body.version)
    item = session.scalar(
        select(SelectionItem).where(
            SelectionItem.id == body.selection_item_id, SelectionItem.request_id == request_id
        )
    )
    if item is None:
        raise ApiError(404, "not_found", "Тур подборки не найден")
    current_selection(session, request, item.selection_id)
    if request.selected_selection_item_id != item.id:
        request.selected_selection_item_id = item.id
        request.version += 1
    return requests.finish(session, actor, request, operation, command)


def issue_link(session, actor, selection_id, base_url):
    row = get_visible(session, actor, selection_id)
    request = requests.locked_request(session, actor, row.request_id)
    current_selection(session, request, selection_id)
    now = session.scalar(select(func.clock_timestamp()))
    session.execute(
        update(PublicLink)
        .where(PublicLink.selection_id == selection_id, PublicLink.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    token, digest = new_token()
    link = PublicLink(
        purpose="selection",
        selection_id=selection_id,
        request_id=None,
        token_hash=digest,
        created_by_id=actor.id,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    session.add(link)
    session.flush()
    result = PublicLinkDto(
        id=link.id,
        purpose=link.purpose,
        url=f"{base_url}/public/selections/{token}",
        expires_at=link.expires_at,
    )
    session.commit()
    return result


def revoke_link(session, actor, identity):
    link = session.get(PublicLink, identity)
    if link is None:
        raise ApiError(404, "not_found", "Ссылка не найдена")
    try:
        request_id = (
            get_visible(session, actor, link.selection_id).request_id
            if link.purpose == "selection"
            else link.request_id
        )
        requests.locked_request(session, actor, request_id)
    except ApiError as error:
        if error.status == 404:
            raise ApiError(404, "not_found", "Ссылка не найдена") from None
        raise
    link = session.scalar(
        select(PublicLink)
        .where(PublicLink.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if link.revoked_at is None:
        link.revoked_at = session.scalar(select(func.clock_timestamp()))
    session.commit()


def public_selection(session, token):
    digest = token_hash(token)
    if digest is None:
        raise ApiError(404, "not_found", "Подборка недоступна")
    link = session.scalar(
        select(PublicLink).where(
            PublicLink.token_hash == digest,
            PublicLink.purpose == "selection",
            PublicLink.revoked_at.is_(None),
            PublicLink.expires_at > func.clock_timestamp(),
        )
    )
    if link is None:
        raise ApiError(404, "not_found", "Подборка недоступна")
    rows = session.scalars(
        select(SelectionItem)
        .where(SelectionItem.selection_id == link.selection_id)
        .order_by(SelectionItem.position, SelectionItem.id)
    ).all()
    return PublicSelection(
        items=[PublicSelectionItem(id=row.id, offer_snapshot=row.offer_snapshot) for row in rows],
        expires_at=link.expires_at,
    )
