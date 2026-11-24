from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi import Request as HttpRequest

from app.core.database import DbSession
from app.core.errors import Error
from app.core.idempotency import IdempotentCommand
from app.core.link_schemas import PublicLink
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.tourists import service
from app.modules.tourists.schemas import (
    PublicTouristForm,
    Tourist,
    TouristSubmission,
    TouristSubmissionResult,
)

Staff = Annotated[User, Depends(require_roles(Role.MANAGER, Role.HEAD))]
router = APIRouter(
    tags=["tourists"],
    responses={code: {"model": Error} for code in (401, 403, 404, 409, 422, 503)},
)
public_router = APIRouter(
    tags=["public"], responses={code: {"model": Error} for code in (404, 409, 422, 503)}
)


def privacy(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


@router.get(
    "/api/requests/{request_id}/tourists",
    response_model=list[Tourist],
    operation_id="get_request_tourists",
)
def get_tourists(request_id: UUID, actor: Staff, session: DbSession, response: Response):
    privacy(response)
    return service.list_tourists(session, actor, request_id)


@router.put(
    "/api/requests/{request_id}/tourists",
    response_model=TouristSubmissionResult,
    operation_id="replace_request_tourists",
)
def replace_tourists(
    request_id: UUID,
    actor: Staff,
    session: DbSession,
    body: TouristSubmission,
    command: IdempotentCommand,
    response: Response,
):
    privacy(response)
    return service.replace_staff(session, actor, request_id, body, command)


@router.post(
    "/api/requests/{request_id}/tourist-link",
    response_model=PublicLink,
    status_code=201,
    operation_id="issue_tourist_link",
)
def issue_link(
    request_id: UUID,
    actor: Staff,
    session: DbSession,
    request: HttpRequest,
    response: Response,
):
    privacy(response)
    return service.issue_link(session, actor, request_id, request.app.state.settings.public_app_url)


@public_router.get(
    "/api/public/tourist-forms/{token}",
    response_model=PublicTouristForm,
    operation_id="get_public_tourist_form",
)
def public_form(token: str, session: DbSession):
    return service.public_form(session, token)


@public_router.put(
    "/api/public/tourist-forms/{token}",
    response_model=TouristSubmissionResult,
    operation_id="submit_public_tourists",
)
def submit_public(
    token: str, session: DbSession, body: TouristSubmission, command: IdempotentCommand
):
    return service.replace_public(session, token, body, command)
