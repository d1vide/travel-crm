import hmac
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request, Response

from app.core.database import DbSession
from app.core.errors import ApiError
from app.modules.payments.adapter import ProviderPayment
from app.modules.payments.models import Payment
from app.modules.payments.service import apply_result


class PaymentEvent(ProviderPayment):
    status: Literal["succeeded", "failed"]


def require_sender(request: Request, authorization: Annotated[str | None, Header()] = None):
    adapter = request.app.state.payment_adapter
    expected = (
        ("Bearer " + adapter.settings.payment_stub_key.get_secret_value()).encode()
        if adapter.configured()
        else b""
    )
    if not expected or not hmac.compare_digest((authorization or "").encode(), expected):
        raise ApiError(401, "unauthorized", "Недоступный источник результата оплаты")


router = APIRouter(include_in_schema=False, dependencies=[Depends(require_sender)])


@router.post("/internal/payment-events", status_code=204)
def payment_event(body: PaymentEvent, session: DbSession, request: Request):
    adapter = request.app.state.payment_adapter
    row = session.get(Payment, body.client_operation_id)
    if row is None:
        raise ApiError(404, "not_found", "Платёж не найден")
    if (
        body.amount != f"{row.amount:.2f}"
        or body.currency != row.currency
        or (row.external_operation_id is not None and row.external_operation_id != str(body.id))
    ):
        raise ApiError(409, "conflict", "Результат не соответствует платежу")
    apply_result(session, row.id, body, None, adapter)
    if session.get(Payment, row.id).status == "pending":
        raise ApiError(409, "conflict", "Результат требует сверки")
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
