from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.database import DbSession
from app.core.errors import Error
from app.core.idempotency import IdempotentCommand
from app.core.pagination import HistoryQuery
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.requests import service
from app.modules.requests.schemas import (
    AssignRequest,
    AuditRecordPage,
    ExpectedVersion,
    ReasonCommand,
    Request,
    RequestCreate,
    RequestPage,
    RequestQuery,
    RequestUpdate,
)

Staff = Annotated[User, Depends(require_roles(Role.MANAGER, Role.HEAD))]
Head = Annotated[User, Depends(require_roles(Role.HEAD))]
router = APIRouter(
    prefix="/api/requests",
    tags=["requests"],
    responses={code: {"model": Error} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get("", response_model=RequestPage, operation_id="list_requests")
def list_requests(actor: Staff, session: DbSession, query: Annotated[RequestQuery, Query()]):
    return service.list_requests(session, actor, query)


@router.post("", response_model=Request, status_code=201, operation_id="create_request")
def create_request(
    actor: Staff, body: RequestCreate, session: DbSession, command: IdempotentCommand
):
    return service.create_request(session, actor, body, command)


@router.get("/{request_id}", response_model=Request, operation_id="get_request")
def get_request(request_id: UUID, actor: Staff, session: DbSession):
    return service.card(session, actor, service.get_visible(session, actor, request_id))


@router.put("/{request_id}", response_model=Request, operation_id="update_request")
def update_request(
    request_id: UUID,
    actor: Staff,
    body: RequestUpdate,
    session: DbSession,
    command: IdempotentCommand,
):
    return service.mutate_request(session, actor, request_id, body, command, "update")


@router.patch("/{request_id}/assignee", response_model=Request, operation_id="assign_request")
def assign_request(
    request_id: UUID,
    actor: Head,
    body: AssignRequest,
    session: DbSession,
    command: IdempotentCommand,
):
    return service.mutate_request(session, actor, request_id, body, command, "assign")


@router.post(
    "/{request_id}/actions/start-work", response_model=Request, operation_id="start_work_request"
)
def start_work(
    request_id: UUID,
    actor: Staff,
    body: ExpectedVersion,
    session: DbSession,
    command: IdempotentCommand,
):
    return service.mutate_request(session, actor, request_id, body, command, "start-work")


@router.post("/{request_id}/actions/cancel", response_model=Request, operation_id="cancel_request")
def cancel(
    request_id: UUID,
    actor: Staff,
    body: ReasonCommand,
    session: DbSession,
    command: IdempotentCommand,
):
    return service.mutate_request(session, actor, request_id, body, command, "cancel")


@router.post("/{request_id}/actions/resume", response_model=Request, operation_id="resume_request")
def resume(
    request_id: UUID,
    actor: Staff,
    body: ExpectedVersion,
    session: DbSession,
    command: IdempotentCommand,
):
    return service.mutate_request(session, actor, request_id, body, command, "resume")


@router.post(
    "/{request_id}/actions/return-to-work",
    response_model=Request,
    operation_id="return_to_work_request",
)
def return_to_work(
    request_id: UUID,
    actor: Staff,
    body: ExpectedVersion,
    session: DbSession,
    command: IdempotentCommand,
):
    return service.mutate_request(session, actor, request_id, body, command, "return-to-work")


@router.get(
    "/{request_id}/history", response_model=AuditRecordPage, operation_id="list_request_history"
)
def history(
    request_id: UUID, actor: Staff, session: DbSession, query: Annotated[HistoryQuery, Query()]
):
    return service.list_history(session, actor, request_id, query)
