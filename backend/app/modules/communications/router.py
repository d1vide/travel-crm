from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.database import DbSession
from app.core.errors import Error
from app.core.idempotency import IdempotentCommand
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.communications import service
from app.modules.communications.schemas import (
    Communication,
    CommunicationCreate,
    CommunicationPage,
    CommunicationQuery,
)

Staff = Annotated[User, Depends(require_roles(Role.MANAGER, Role.HEAD))]
router = APIRouter(
    tags=["communications"],
    responses={code: {"model": Error} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/api/clients/{client_id}/communications",
    response_model=CommunicationPage,
    operation_id="list_client_communications",
)
def list_client(
    client_id: UUID, actor: Staff, session: DbSession, query: Annotated[CommunicationQuery, Query()]
):
    return service.list_client(session, actor, client_id, query)


@router.post(
    "/api/clients/{client_id}/communications",
    response_model=Communication,
    status_code=201,
    operation_id="create_communication",
)
def create(
    client_id: UUID,
    actor: Staff,
    body: CommunicationCreate,
    session: DbSession,
    command: IdempotentCommand,
):
    return service.create(session, actor, client_id, body, command)


@router.get(
    "/api/requests/{request_id}/communications",
    response_model=CommunicationPage,
    operation_id="list_request_communications",
)
def list_request(
    request_id: UUID,
    actor: Staff,
    session: DbSession,
    query: Annotated[CommunicationQuery, Query()],
):
    return service.list_request(session, actor, request_id, query)
