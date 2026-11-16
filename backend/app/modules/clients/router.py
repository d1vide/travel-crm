from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.database import DbSession
from app.core.errors import Error
from app.core.idempotency import IdempotentCommand
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.clients import service
from app.modules.clients.schemas import (
    Client,
    ClientCreate,
    ClientListQuery,
    ClientPage,
    ClientUpdate,
    DuplicateCheckResult,
    DuplicateQuery,
)

Staff = Annotated[User, Depends(require_roles(Role.MANAGER, Role.HEAD))]
router = APIRouter(
    prefix="/api/clients",
    tags=["clients"],
    responses={
        401: {"model": Error},
        403: {"model": Error},
        404: {"model": Error},
        409: {"model": Error},
        422: {"model": Error},
        503: {"model": Error},
    },
)


@router.get("", response_model=ClientPage, operation_id="list_clients")
def list_clients(actor: Staff, session: DbSession, query: Annotated[ClientListQuery, Query()]):
    return service.list_clients(session, actor, query)


@router.get(
    "/duplicates", response_model=DuplicateCheckResult, operation_id="check_duplicate_clients"
)
def check_duplicates(actor: Staff, session: DbSession, query: Annotated[DuplicateQuery, Query()]):
    return service.duplicates(session, actor, query)


@router.post("", response_model=Client, status_code=201, operation_id="create_client")
def create_client(actor: Staff, body: ClientCreate, session: DbSession, command: IdempotentCommand):
    return service.create_client(session, actor, body, command)


@router.get("/{client_id}", response_model=Client, operation_id="get_client")
def get_client(client_id: UUID, actor: Staff, session: DbSession):
    return service.card(service.get_visible(session, actor, client_id))


@router.put("/{client_id}", response_model=Client, operation_id="update_client")
def update_client(
    client_id: UUID,
    actor: Staff,
    body: ClientUpdate,
    session: DbSession,
    command: IdempotentCommand,
):
    return service.update_client(session, actor, client_id, body, command)
