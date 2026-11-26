import asyncio
import hashlib
import hmac
import re
import time
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from sqlalchemy import func, select

from stubs.delivery import Delivery
from stubs.protocol import dto, token
from stubs.refunds import register as register_refunds
from stubs.store import Operation, Settings, database

HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


class CreateOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    client_operation_id: UUID
    amount: StrictStr = Field(pattern=r"^(0|[1-9][0-9]{0,11})\.[0-9]{2}$")
    currency: Literal["RUB"]

    @field_validator("amount")
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Positive amount required")
        return value


def create_app(settings=None):
    settings = settings or Settings()
    engine, sessions = database(settings)

    @asynccontextmanager
    async def lifespan(_app):
        worker = Delivery(settings, sessions) if settings.payment_callback_url else None
        task = asyncio.create_task(worker.run()) if worker else None
        try:
            yield
        finally:
            try:
                if worker:
                    worker.stop.set()
                    await task
            finally:
                engine.dispose()

    app = FastAPI(
        title="Payment simulator",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.engine = engine

    @app.middleware("http")
    async def privacy(request, call_next):
        response = await call_next(request)
        response.headers.update(HEADERS)
        return response

    def authorize(authorization: Annotated[str | None, Header()] = None):
        if not hmac.compare_digest(
            (authorization or "").encode(),
            ("Bearer " + settings.payment_stub_key.get_secret_value()).encode(),
        ):
            raise HTTPException(401, "Unauthorized")

    @app.get("/healthz")
    def health():
        with sessions() as session:
            session.scalar(select(Operation.id).limit(1))
        return {"status": "ok"}

    @app.post("/v1/payments", dependencies=[Depends(authorize)])
    def create(body: CreateOperation):
        with sessions.begin() as session:
            key = int.from_bytes(
                hashlib.sha256(body.client_operation_id.bytes).digest()[:8],
                "big",
                signed=True,
            )
            session.scalar(select(func.pg_advisory_xact_lock(key)))
            row = session.scalar(
                select(Operation).where(Operation.client_operation_id == body.client_operation_id)
            )
            if row is not None:
                if row.amount != Decimal(body.amount) or row.currency != body.currency:
                    raise HTTPException(409, "Operation payload differs")
            else:
                raw = token(settings, body.client_operation_id)
                row = Operation(
                    client_operation_id=body.client_operation_id,
                    amount=Decimal(body.amount),
                    currency=body.currency,
                    token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                )
                session.add(row)
                session.flush()
            result = dto(settings, row)
        return result

    @app.get("/v1/payments/{identity}", dependencies=[Depends(authorize)])
    def read(identity: UUID):
        with sessions() as session:
            row = session.get(Operation, identity)
            if row is None:
                raise HTTPException(404, "Operation not found")
            result = dto(settings, row)
            delayed = row.simulate_timeout
        if delayed:
            time.sleep(settings.stub_timeout_seconds)
        return result

    def find(session, raw, *, lock=False):
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", raw):
            raise HTTPException(404, "Платёж недоступен")
        query = select(Operation).where(
            Operation.token_hash == hashlib.sha256(raw.encode()).hexdigest()
        )
        row = session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise HTTPException(404, "Платёж недоступен")
        return row

    def page(row):
        labels = {
            "pending": "Ожидает оплаты",
            "succeeded": "Оплата успешна",
            "failed": "Платёж отклонён",
        }
        buttons = (
            "".join(
                f'<button name="outcome" value="{value}">{label}</button>'
                for value, label in (
                    ("succeeded", "Успех"),
                    ("failed", "Отказ"),
                    ("timeout", "Тайм-аут"),
                )
            )
            if row.status == "pending"
            else ""
        )
        return HTMLResponse(
            f'<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Тестовая оплата</title><style>body{{font:18px system-ui;max-width:640px;margin:10vh auto;padding:24px;color:#18243b;background:#f5f7fa}}main{{background:white;border-radius:16px;padding:32px}}button{{padding:12px 18px;margin:8px 8px 0 0;border:0;border-radius:8px;background:#234fc7;color:white;font-size:16px}}</style><main><h1>Тестовая оплата</h1><p>{row.amount:.2f} RUB</p><p>{labels[row.status]}</p><p>Реальные деньги не списываются. Выберите тестовый исход.</p><form id="checkout" method="post">{buttons}</form><p id="checkout-error" role="alert" hidden></p><script src="/payment-stub/checkout.js" defer></script></main></html>',
            headers=HEADERS,
        )

    @app.get("/payment-stub/pay/{raw}")
    def checkout(raw: str):
        with sessions() as session:
            return page(find(session, raw))

    @app.get("/payment-stub/checkout.js")
    def checkout_script():
        return FileResponse(
            Path(__file__).with_name("checkout.js"),
            media_type="application/javascript",
            headers=HEADERS,
        )

    @app.post("/payment-stub/pay/{raw}")
    async def choose(raw: str, request: Request):
        if request.headers.get("origin") != settings.public_app_url.rstrip("/"):
            raise HTTPException(403, "Откройте форму на адресе приложения")
        data = await request.body()
        if len(data) > 256:
            raise HTTPException(400, "Invalid outcome")
        fields = parse_qs(data.decode("ascii", errors="replace"))
        if (
            set(fields) != {"outcome"}
            or len(fields["outcome"]) != 1
            or fields["outcome"][0] not in ("succeeded", "failed", "timeout")
        ):
            raise HTTPException(400, "Invalid outcome")
        outcome = fields["outcome"][0]
        with sessions.begin() as session:
            row = find(session, raw, lock=True)
            if row.status != "pending" and outcome != row.status:
                raise HTTPException(409, "Результат уже сохранён")
            if row.status == "pending":
                row.simulate_timeout = outcome == "timeout"
                if outcome != "timeout":
                    row.status = outcome
                    if outcome == "succeeded":
                        row.succeeded_at = session.scalar(select(func.clock_timestamp()))
            if outcome in ("succeeded", "failed"):
                row.delivery_pending = True
                row.next_delivery_at = session.scalar(select(func.clock_timestamp()))
            return page(row)

    register_refunds(app, settings, sessions, authorize, CreateOperation)
    return app
