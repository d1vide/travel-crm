from datetime import timedelta

from sqlalchemy import func, select, update

from app.core.errors import ApiError, FieldError
from app.core.idempotency import check_payload, find_previous, remember
from app.core.link_schemas import PublicLink as LinkDto
from app.core.public_links import PublicLink, new_token, token_hash
from app.modules.bookings.access import active_condition
from app.modules.clients.models import Client
from app.modules.requests import service as requests
from app.modules.requests.access import request_is_visible
from app.modules.requests.models import TravelRequest
from app.modules.tourists import views
from app.modules.tourists.models import Tourist
from app.modules.tourists.schemas import PublicTouristForm, TouristSubmissionResult
from app.modules.tourists.schemas import Tourist as TouristDto

FIELDS = ("full_name", "birth_date", "document_type", "document_number", "document_expires_on")


def list_tourists(session, actor, identity):
    requests.get_visible(session, actor, identity)
    return [
        TouristDto.model_validate(row)
        for row in session.scalars(
            select(Tourist)
            .where(
                Tourist.request_id == identity,
                Tourist.removed_at.is_(None),
                request_is_visible(Tourist.request_id, actor),
            )
            .order_by(Tourist.position, Tourist.id)
        )
    ]


def ensure_editable(session, request):
    if not views.is_editable(request, session.scalar(select(active_condition(request.id)))):
        raise ApiError(409, "tourist_form_closed", "Изменение данных туристов сейчас недоступно")


def issue_link(session, actor, identity, base_url):
    request = requests.locked_request(session, actor, identity)
    ensure_editable(session, request)
    now = session.scalar(select(func.clock_timestamp()))
    session.execute(
        update(PublicLink)
        .where(PublicLink.request_id == identity, PublicLink.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    token, digest = new_token()
    link = PublicLink(
        purpose="tourists",
        request_id=identity,
        token_hash=digest,
        created_by_id=actor.id,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    session.add(link)
    session.flush()
    result = LinkDto(
        id=link.id,
        purpose="tourists",
        url=f"{base_url}/public/tourist-forms/{token}",
        expires_at=link.expires_at,
    )
    session.commit()
    return result


def active_link(session, token, *, lock=False):
    digest = token_hash(token)
    if digest is None:
        raise ApiError(404, "not_found", "Форма недоступна")
    query = select(PublicLink).where(
        PublicLink.token_hash == digest,
        PublicLink.purpose == "tourists",
        PublicLink.revoked_at.is_(None),
        PublicLink.expires_at > func.clock_timestamp(),
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = session.scalar(query)
    if row is None:
        raise ApiError(404, "not_found", "Форма недоступна")
    return row


def public_form(session, token):
    # One statement keeps activity and request state in the same database snapshot.
    digest = token_hash(token)
    found = (
        session.execute(
            select(
                PublicLink, TravelRequest, active_condition(TravelRequest.id).label("has_booking")
            )
            .join(TravelRequest, TravelRequest.id == PublicLink.request_id)
            .where(
                PublicLink.token_hash == digest,
                PublicLink.purpose == "tourists",
                PublicLink.revoked_at.is_(None),
                PublicLink.expires_at > func.clock_timestamp(),
            )
        ).first()
        if digest is not None
        else None
    )
    if found is None:
        raise ApiError(404, "not_found", "Форма недоступна")
    link, request, has_booking = found
    editable = views.is_editable(request, has_booking)
    return PublicTouristForm(
        tourist_count=request.tourist_count,
        request_version=request.version,
        expires_at=link.expires_at,
        is_editable=editable,
        closed_reason=None if editable else "Изменение данных туристов сейчас недоступно",
    )


def replace(session, request, body):
    ensure_editable(session, request)
    requests.expect_version(request, body.request_version)
    if len(body.tourists) != request.tourist_count:
        raise ApiError(
            422,
            "validation_error",
            "Проверьте данные",
            [
                FieldError(
                    field="tourists", message="Передайте полный список по числу туристов заявки"
                )
            ],
        )
    ids = [item.id for item in body.tourists if item.id is not None]
    if len(ids) != len(set(ids)):
        raise ApiError(
            422,
            "validation_error",
            "Проверьте данные",
            [FieldError(field="tourists", message="Идентификаторы туристов не должны повторяться")],
        )
    rows = {
        row.id: row
        for row in session.scalars(
            select(Tourist)
            .where(Tourist.request_id == request.id, Tourist.removed_at.is_(None))
            .execution_options(populate_existing=True)
        )
    }
    if not set(ids) <= rows.keys():
        raise ApiError(404, "not_found", "Турист не найден")
    for item in body.tourists:
        if item.id is not None:
            row = rows[item.id]
            if row.version >= 2_147_483_647:
                raise ApiError(409, "conflict", "Достигнут предел версии туриста")
    now = session.scalar(select(func.clock_timestamp()))
    for row in rows.values():
        if row.id not in ids:
            row.removed_at = now
    for position, item in enumerate(body.tourists):
        row = rows.get(item.id)
        if row is None:
            row = Tourist(request_id=request.id, position=position)
            session.add(row)
        elif row.position != position or any(
            getattr(row, field) != getattr(item, field) for field in FIELDS
        ):
            row.version += 1
        row.position = position
        for field in FIELDS:
            setattr(row, field, getattr(item, field))
    request.version += 1
    session.flush()
    return TouristSubmissionResult(
        accepted_count=len(body.tourists), request_version=request.version
    )


def replay(previous, command, identity):
    if previous.resource_type != "tourists" or previous.resource_id != identity:
        raise ApiError(409, "idempotency_conflict", "Ключ принадлежит другой операции")
    check_payload(previous, command)
    return TouristSubmissionResult.model_validate(previous.result_metadata)


def finish(session, scope, operation, command, request, body, previous):
    if previous is not None:
        result = replay(previous, command, request.id)
    else:
        result = replace(session, request, body)
        remember(
            session,
            scope,
            operation,
            command,
            resource_type="tourists",
            resource_id=request.id,
            result_metadata=result.model_dump(mode="json"),
        )
    session.commit()
    return result


def replace_staff(session, actor, identity, body, command):
    requests.get_visible(session, actor, identity)
    scope = f"staff:{actor.id}"
    operation = f"PUT /api/requests/{identity}/tourists"
    previous = find_previous(session, scope, operation, command)
    request = requests.locked_request(session, actor, identity)
    return finish(session, scope, operation, command, request, body, previous)


def replace_public(session, token, body, command):
    initial = active_link(session, token)
    scope = f"public-link:{initial.id}"
    # The token must never enter persisted command metadata.
    operation = "PUT /api/public/tourist-forms/{token}"
    previous = find_previous(session, scope, operation, command)
    initial_request = session.get(TravelRequest, initial.request_id)
    session.scalar(select(Client).where(Client.id == initial_request.client_id).with_for_update())
    request = session.scalar(
        select(TravelRequest)
        .where(TravelRequest.id == initial.request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    active_link(session, token, lock=True)
    return finish(session, scope, operation, command, request, body, previous)
