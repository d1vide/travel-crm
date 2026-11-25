from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.database import DbSession
from app.core.errors import Error
from app.core.idempotency import IdempotentCommand
from app.core.pagination import HistoryQuery
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.payments import service
from app.modules.payments.schemas import Payment, PaymentCreate, PaymentPage, PaymentQuery

Staff = Annotated[User, Depends(require_roles(Role.MANAGER, Role.HEAD))]
Reader = Annotated[User, Depends(require_roles(Role.MANAGER, Role.HEAD, Role.ACCOUNTANT))]
Finance = Annotated[User, Depends(require_roles(Role.HEAD, Role.ACCOUNTANT))]


def privacy(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


router = APIRouter(
    tags=["payments"],
    dependencies=[Depends(privacy)],
    responses={code: {"model": Error} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get("/api/payments", response_model=PaymentPage, operation_id="list_payments")
def list_payments(actor: Finance, session: DbSession, query: Annotated[PaymentQuery, Query()]):
    return service.list_payments(session, actor, query)


@router.get(
    "/api/bookings/{booking_id}/payments",
    response_model=PaymentPage,
    operation_id="list_booking_payments",
)
def list_booking_payments(
    booking_id: UUID, actor: Staff, session: DbSession, query: Annotated[HistoryQuery, Query()]
):
    return service.list_payments(session, actor, query, booking_id)


@router.post(
    "/api/bookings/{booking_id}/payments",
    response_model=Payment,
    status_code=202,
    operation_id="create_payment",
)
def create_payment(
    booking_id: UUID,
    actor: Staff,
    session: DbSession,
    body: PaymentCreate,
    command: IdempotentCommand,
    request: Request,
):
    return service.create_payment(
        session, actor, booking_id, body, command, request.app.state.payment_adapter
    )


@router.get("/api/payments/{payment_id}", response_model=Payment, operation_id="get_payment")
def get_payment(payment_id: UUID, actor: Reader, session: DbSession, request: Request):
    return service.synchronize(session, actor, payment_id, request.app.state.payment_adapter)


@router.post(
    "/api/payments/{payment_id}/reconcile",
    response_model=Payment,
    status_code=202,
    operation_id="reconcile_payment",
)
def reconcile(payment_id: UUID, actor: Staff, session: DbSession, request: Request):
    return service.synchronize(session, actor, payment_id, request.app.state.payment_adapter)
