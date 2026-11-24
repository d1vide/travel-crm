from sqlalchemy import func, or_, select

from app.core.errors import ApiError
from app.core.idempotency import check_payload, find_previous, remember
from app.modules.auth.directory import user_briefs
from app.modules.auth.models import Role
from app.modules.clients import service as clients
from app.modules.communications.models import Communication as Record
from app.modules.communications.schemas import Communication, CommunicationPage
from app.modules.requests import service as requests
from app.modules.requests.access import request_is_visible


def visible_records(actor):
    if actor.role == Role.HEAD:
        return clients.client_is_visible(Record.client_id, actor)
    return clients.client_is_visible(Record.client_id, actor) & or_(
        Record.request_id.is_(None), request_is_visible(Record.request_id, actor)
    )


def project(session, rows):
    authors = user_briefs(session, {row.author_id for row in rows})
    return [
        Communication(
            id=row.id,
            client_id=row.client_id,
            request_id=row.request_id,
            author_id=row.author_id,
            channel=row.channel,
            text=row.text,
            occurred_at=row.occurred_at,
            created_at=row.created_at,
            author=authors[row.author_id],
        )
        for row in rows
    ]


def page(session, actor, conditions, query):
    conditions = [*conditions, visible_records(actor)]
    total = session.scalar(select(func.count()).select_from(Record).where(*conditions))
    rows = session.scalars(
        select(Record)
        .where(*conditions)
        .order_by(Record.occurred_at.desc(), Record.id.desc())
        .offset(query.offset)
        .limit(query.page_size)
    ).all()
    return CommunicationPage(
        items=project(session, rows), page=query.page, page_size=query.page_size, total=total
    )


def list_client(session, actor, identity, query):
    clients.get_visible(session, actor, identity)
    return page(session, actor, [Record.client_id == identity], query)


def list_request(session, actor, identity, query):
    requests.get_visible(session, actor, identity)
    return page(session, actor, [Record.request_id == identity], query)


def authorize_link(session, actor, client_id, request_id, *, lock=False):
    if request_id is not None:
        request = requests.get_visible(session, actor, request_id, lock=lock)
        if request.client_id != client_id:
            raise ApiError(422, "validation_error", "Заявка не относится к этому клиенту")


def create(session, actor, client_id, body, command):
    clients.get_visible(session, actor, client_id)
    operation = f"POST /api/clients/{client_id}/communications"
    scope = f"staff:{actor.id}"
    previous = find_previous(session, scope, operation, command)
    if previous is not None:
        clients.get_visible(session, actor, client_id, lock=True)
        row = session.scalar(
            select(Record).where(Record.id == previous.resource_id, Record.client_id == client_id)
        )
        if previous.resource_type != "communication" or row is None:
            raise ApiError(404, "not_found", "Запись не найдена")
        authorize_link(session, actor, client_id, row.request_id, lock=True)
        check_payload(previous, command)
        result = project(session, [row])[0]
        session.commit()
        return result
    # Reject a mismatched request before taking its lock, then recheck under the parent lock.
    authorize_link(session, actor, client_id, body.request_id)
    clients.get_visible(session, actor, client_id, lock=True)
    authorize_link(session, actor, client_id, body.request_id, lock=True)
    row = Record(
        client_id=client_id,
        request_id=body.request_id,
        author_id=actor.id,
        channel=body.channel,
        text=body.text,
        occurred_at=body.occurred_at,
    )
    session.add(row)
    session.flush()
    remember(session, scope, operation, command, resource_type="communication", resource_id=row.id)
    result = project(session, [row])[0]
    session.commit()
    return result
