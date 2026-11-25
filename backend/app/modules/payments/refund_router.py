from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.core.database import DbSession
from app.core.errors import Error
from app.core.idempotency import IdempotentCommand
from app.core.pagination import HistoryQuery
from app.modules.payments import refunds
from app.modules.payments.refund_schemas import Refund, RefundCreate, RefundPage, RefundQuery
from app.modules.payments.router import Finance, Reader, Staff, privacy

router = APIRouter(
    tags=["refunds"],
    dependencies=[Depends(privacy)],
    responses={code: {"model": Error} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get("/api/refunds", response_model=RefundPage, operation_id="list_refunds")
def list_refunds(actor: Finance, session: DbSession, query: Annotated[RefundQuery, Query()]):
    return refunds.list_refunds(session, actor, query)


@router.get(
    "/api/payments/{payment_id}/refunds",
    response_model=RefundPage,
    operation_id="list_payment_refunds",
)
def list_payment_refunds(
    payment_id: UUID, actor: Reader, session: DbSession, query: Annotated[HistoryQuery, Query()]
):
    return refunds.list_refunds(session, actor, query, payment_id)


@router.post(
    "/api/payments/{payment_id}/refunds",
    response_model=Refund,
    operation_id="create_refund",
    status_code=202,
)
def create_refund(
    payment_id: UUID,
    actor: Staff,
    session: DbSession,
    body: RefundCreate,
    command: IdempotentCommand,
    request: Request,
):
    return refunds.create(
        session, actor, payment_id, body, command, request.app.state.payment_adapter
    )


@router.get("/api/refunds/{refund_id}", response_model=Refund, operation_id="get_refund")
def get_refund(refund_id: UUID, actor: Reader, session: DbSession, request: Request):
    return refunds.synchronize(session, actor, refund_id, request.app.state.payment_adapter)


@router.post(
    "/api/refunds/{refund_id}/reconcile",
    response_model=Refund,
    operation_id="reconcile_refund",
    status_code=202,
)
def reconcile(refund_id: UUID, actor: Staff, session: DbSession, request: Request):
    return refunds.synchronize(session, actor, refund_id, request.app.state.payment_adapter)
