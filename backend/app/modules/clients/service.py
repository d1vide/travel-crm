from uuid import UUID

from sqlalchemy import and_, exists, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.idempotency import CommandIdentity, check_payload, find_previous, remember
from app.core.locking import lock_contacts
from app.modules.auth.models import User
from app.modules.clients.access import visible_clients
from app.modules.clients.models import Client as ClientRecord
from app.modules.clients.normalization import contains_pattern, normalize_name, search_phone
from app.modules.clients.schemas import (
    Client,
    ClientAction,
    ClientBrief,
    ClientCreate,
    ClientListQuery,
    ClientPage,
    ClientUpdate,
    DuplicateCheckResult,
    DuplicateQuery,
)


def get_visible(session: Session, actor: User, client_id: UUID, *, lock=False) -> ClientRecord:
    query = select(ClientRecord).where(ClientRecord.id == client_id, visible_clients(actor))
    if lock:
        query = query.with_for_update(of=ClientRecord).execution_options(populate_existing=True)
    client = session.scalar(query)
    if client is None:
        raise ApiError(404, "not_found", "Клиент не найден")
    # A parent row lock does not refresh EXISTS subqueries evaluated before waiting.
    if lock and not session.scalar(
        select(
            exists().where(
                ClientRecord.id == client_id,
                visible_clients(actor),
            )
        )
    ):
        raise ApiError(404, "not_found", "Клиент не найден")
    return client


def client_is_visible(client_id, actor):
    return exists(
        select(ClientRecord.id)
        .where(
            ClientRecord.id == client_id,
            visible_clients(actor),
        )
        .correlate_except(ClientRecord)
    )


def card(client: ClientRecord) -> Client:
    return Client(
        id=client.id,
        client_number=client.client_number,
        full_name=client.full_name,
        phone=client.phone,
        email=client.email,
        preferences=client.preferences,
        note=client.note,
        version=client.version,
        created_at=client.created_at,
        updated_at=client.updated_at,
        allowed_actions=[ClientAction.UPDATE, ClientAction.CREATE_REQUEST],
    )


def request_client_briefs(session: Session, identities) -> dict:
    """Project clients for requests whose object access has already been checked."""
    rows = session.execute(
        select(ClientRecord.id, ClientRecord.client_number, ClientRecord.full_name).where(
            ClientRecord.id.in_(identities)
        )
    )
    return {row.id: ClientBrief(**row._mapping) for row in rows}


def list_clients(session: Session, actor: User, query: ClientListQuery) -> ClientPage:
    conditions = [visible_clients(actor)]
    if query.q:
        filters = [
            ClientRecord.full_name_normalized.like(
                contains_pattern(normalize_name(query.q)), escape="\\"
            ),
            ClientRecord.email_normalized.like(contains_pattern(query.q.lower()), escape="\\"),
        ]
        digits = search_phone(query.q)
        if digits:
            filters.append(
                ClientRecord.phone_normalized.like(contains_pattern(digits), escape="\\")
            )
        conditions.append(or_(*filters))
    ordering = {
        "-created_at": (ClientRecord.created_at.desc(), ClientRecord.id.desc()),
        "full_name": (ClientRecord.full_name_normalized.asc(), ClientRecord.id.asc()),
        "client_number": (ClientRecord.client_number.asc(), ClientRecord.id.asc()),
    }[query.sort]
    total = session.scalar(select(func.count()).select_from(ClientRecord).where(*conditions))
    clients = session.scalars(
        select(ClientRecord)
        .where(*conditions)
        .order_by(*ordering)
        .offset((query.page - 1) * query.page_size)
        .limit(query.page_size)
    )
    return ClientPage(
        items=[card(client) for client in clients],
        page=query.page,
        page_size=query.page_size,
        total=total,
    )


def contact_predicate(contacts: set[tuple[str, str]], exclude: UUID | None = None):
    columns = {"phone": ClientRecord.phone_normalized, "email": ClientRecord.email_normalized}
    terms = [columns[kind] == value for kind, value in contacts]
    match = or_(*terms) if terms else false()
    return and_(match, ClientRecord.id != exclude) if exclude is not None else match


def duplicates(session: Session, actor: User, query: DuplicateQuery) -> DuplicateCheckResult:
    if query.exclude_client_id is not None:
        get_visible(session, actor, query.exclude_client_id)
    condition = contact_predicate(query.normalized_contacts(), query.exclude_client_id)
    visible = visible_clients(actor)
    rows = session.execute(
        select(ClientRecord.id, ClientRecord.client_number, ClientRecord.full_name)
        .where(condition, visible)
        .order_by(ClientRecord.client_number)
    )
    matches = [ClientBrief(**row._mapping) for row in rows]
    hidden = session.scalar(select(exists().where(condition, ~visible)))
    return DuplicateCheckResult(matches=matches, requires_head_review=bool(hidden))


def check_duplicates(
    session: Session, actor: User, contacts: set[tuple[str, str]], acknowledged: bool, exclude=None
):
    if not contacts:
        return
    condition = contact_predicate(contacts, exclude)
    visible = visible_clients(actor)
    has_visible, has_hidden = session.execute(
        select(exists().where(condition, visible), exists().where(condition, ~visible))
    ).one()
    if has_hidden:
        raise ApiError(
            409,
            "duplicate_requires_head_review",
            "Совпадение контактов требует проверки руководителем",
        )
    if has_visible and not acknowledged:
        raise ApiError(
            409,
            "duplicate_contacts",
            "Проверьте найденных клиентов и подтвердите создание или изменение",
        )


def assign_fields(client: ClientRecord, body: ClientCreate, contacts: set[tuple[str, str]]):
    normalized = dict(contacts)
    client.full_name = body.full_name
    client.full_name_normalized = normalize_name(body.full_name)
    client.phone = body.phone
    client.email = body.email
    client.phone_normalized = normalized.get("phone")
    client.email_normalized = normalized.get("email")
    client.preferences = body.preferences
    client.note = body.note


def replay(session: Session, actor: User, previous, command: CommandIdentity) -> Client:
    if previous.resource_type != "client":
        raise ApiError(409, "idempotency_conflict", "Ключ принадлежит другой операции")
    client = get_visible(session, actor, previous.resource_id, lock=True)
    check_payload(previous, command)
    result = card(client)
    session.commit()
    return result


def create_client(
    session: Session, actor: User, body: ClientCreate, command: CommandIdentity
) -> Client:
    operation = "POST /api/clients"
    scope = f"staff:{actor.id}"
    previous = find_previous(session, scope, operation, command)
    if previous is not None:
        return replay(session, actor, previous, command)
    contacts = body.normalized_contacts()
    lock_contacts(session, contacts)
    check_duplicates(session, actor, contacts, body.duplicate_acknowledged)
    client = ClientRecord(created_by_id=actor.id)
    assign_fields(client, body, contacts)
    session.add(client)
    session.flush()
    remember(session, scope, operation, command, resource_type="client", resource_id=client.id)
    result = card(client)
    session.commit()
    return result


def update_client(
    session: Session, actor: User, client_id: UUID, body: ClientUpdate, command: CommandIdentity
) -> Client:
    get_visible(session, actor, client_id)  # Authorize before looking up a stored command.
    operation = f"PUT /api/clients/{client_id}"
    scope = f"staff:{actor.id}"
    previous = find_previous(session, scope, operation, command)
    if previous is not None:
        return replay(session, actor, previous, command)
    contacts = body.normalized_contacts()
    lock_contacts(session, contacts)
    client = get_visible(session, actor, client_id, lock=True)
    if client.version != body.version:
        raise ApiError(
            409, "version_conflict", "Карточка уже изменена. Обновите данные и повторите действие"
        )
    previous_contacts = {("phone", client.phone_normalized), ("email", client.email_normalized)}
    check_duplicates(
        session, actor, contacts - previous_contacts, body.duplicate_acknowledged, client_id
    )
    assign_fields(client, body, contacts)
    client.version += 1
    session.flush()
    remember(session, scope, operation, command, resource_type="client", resource_id=client.id)
    result = card(client)
    session.commit()
    return result
