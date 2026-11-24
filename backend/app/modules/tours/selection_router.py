from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi import Request as HttpRequest

from app.core.database import DbSession
from app.core.errors import Error
from app.core.idempotency import IdempotentCommand
from app.core.link_schemas import PublicLink
from app.core.pagination import HistoryQuery
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.requests.schemas import Request
from app.modules.tours import selection_service as service
from app.modules.tours.selection_schemas import (
    PublicSelection,
    Selection,
    SelectionCreate,
    SelectionPage,
    SelectTour,
)

Staff = Annotated[User, Depends(require_roles(Role.MANAGER, Role.HEAD))]
router = APIRouter(
    tags=["selections"],
    responses={code: {"model": Error} for code in (401, 403, 404, 409, 422, 503)},
)
public_router = APIRouter(tags=["public"], responses={404: {"model": Error}, 503: {"model": Error}})


@router.get(
    "/api/requests/{request_id}/selections",
    response_model=SelectionPage,
    operation_id="list_request_selections",
)
def list_selections(
    request_id: UUID, actor: Staff, session: DbSession, query: Annotated[HistoryQuery, Query()]
):
    return service.list_selections(session, actor, request_id, query)


@router.post(
    "/api/requests/{request_id}/selections",
    response_model=Selection,
    status_code=201,
    operation_id="create_selection",
)
def create_selection(
    request_id: UUID,
    actor: Staff,
    body: SelectionCreate,
    session: DbSession,
    command: IdempotentCommand,
):
    return service.create_selection(session, actor, request_id, body, command)


@router.get(
    "/api/selections/{selection_id}", response_model=Selection, operation_id="get_selection"
)
def get_selection(selection_id: UUID, actor: Staff, session: DbSession):
    return service.get_selection(session, actor, selection_id)


@router.put(
    "/api/requests/{request_id}/selected-tour",
    response_model=Request,
    operation_id="select_request_tour",
)
def select_tour(
    request_id: UUID, actor: Staff, body: SelectTour, session: DbSession, command: IdempotentCommand
):
    return service.select_tour(session, actor, request_id, body, command)


@router.post(
    "/api/selections/{selection_id}/public-link",
    response_model=PublicLink,
    status_code=201,
    operation_id="issue_selection_link",
)
def issue_link(
    selection_id: UUID, actor: Staff, session: DbSession, request: HttpRequest, response: Response
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return service.issue_link(
        session, actor, selection_id, request.app.state.settings.public_app_url
    )


@router.delete("/api/public-links/{link_id}", status_code=204, operation_id="revoke_public_link")
def revoke_link(link_id: UUID, actor: Staff, session: DbSession):
    service.revoke_link(session, actor, link_id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@public_router.get(
    "/api/public/selections/{token}",
    response_model=PublicSelection,
    operation_id="get_public_selection",
)
def get_public_selection(token: str, session: DbSession):
    return service.public_selection(session, token)
