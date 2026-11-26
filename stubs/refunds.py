import hashlib
import time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from stubs.store import Operation, RefundOperation


def dto(row):
    return {
        "id": str(row.id),
        "client_operation_id": str(row.client_operation_id),
        "payment_id": str(row.payment_id),
        "amount": f"{row.amount:.2f}",
        "currency": row.currency,
        "status": row.status,
        "failure_reason": "Тестовый отказ возврата" if row.status == "failed" else None,
        "succeeded_at": row.succeeded_at.isoformat().replace("+00:00", "Z")
        if row.succeeded_at
        else None,
    }


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    outcome: Literal["succeeded", "failed", "timeout"]


def register(app, settings, sessions, authorize, create_base):
    class CreateRefund(create_base):
        payment_id: UUID

    def set_outcome(session, row, outcome):
        row.simulate_timeout = outcome == "timeout"
        if outcome != "timeout":
            row.status = outcome
            if outcome == "succeeded":
                row.succeeded_at = session.scalar(select(func.clock_timestamp()))

    @app.post("/v1/refunds", dependencies=[Depends(authorize)])
    def create(body: CreateRefund):
        with sessions.begin() as session:
            key = int.from_bytes(
                hashlib.sha256(b"refund:" + body.client_operation_id.bytes).digest()[:8],
                "big",
                signed=True,
            )
            session.scalar(select(func.pg_advisory_xact_lock(key)))
            payment = session.scalar(
                select(Operation).where(Operation.id == body.payment_id).with_for_update()
            )
            if payment is None:
                raise HTTPException(404, "Payment not found")
            row = session.scalar(
                select(RefundOperation).where(
                    RefundOperation.client_operation_id == body.client_operation_id
                )
            )
            if row is not None:
                if (
                    row.payment_id != body.payment_id
                    or row.amount != Decimal(body.amount)
                    or row.currency != body.currency
                ):
                    raise HTTPException(409, "Operation payload differs")
            else:
                reserved = session.scalar(
                    select(func.coalesce(func.sum(RefundOperation.amount), 0)).where(
                        RefundOperation.payment_id == payment.id,
                        RefundOperation.status.in_(("processing", "succeeded")),
                    )
                )
                if (
                    payment.status != "succeeded"
                    or payment.currency != body.currency
                    or reserved + Decimal(body.amount) > payment.amount
                ):
                    raise HTTPException(409, "Refund exceeds available payment")
                row = RefundOperation(
                    client_operation_id=body.client_operation_id,
                    payment_id=payment.id,
                    amount=Decimal(body.amount),
                    currency=body.currency,
                )
                session.add(row)
                set_outcome(session, row, settings.stub_refund_outcome)
                session.flush()
            result, delayed = dto(row), row.simulate_timeout
        if delayed:
            time.sleep(settings.stub_timeout_seconds)
        return result

    @app.get("/v1/refunds/{identity}", dependencies=[Depends(authorize)])
    def read(identity: UUID):
        with sessions() as session:
            row = session.get(RefundOperation, identity)
            if row is None:
                raise HTTPException(404, "Refund not found")
            result, delayed = dto(row), row.simulate_timeout
        if delayed:
            time.sleep(settings.stub_timeout_seconds)
        return result

    @app.post("/v1/refunds/{identity}/outcome", dependencies=[Depends(authorize)])
    def choose(identity: UUID, body: Outcome):
        with sessions.begin() as session:
            row = session.scalar(
                select(RefundOperation).where(RefundOperation.id == identity).with_for_update()
            )
            if row is None:
                raise HTTPException(404, "Refund not found")
            if row.status != "processing" and row.status != body.outcome:
                raise HTTPException(409, "Result already recorded")
            if row.status == "processing":
                set_outcome(session, row, body.outcome)
            return dto(row)
