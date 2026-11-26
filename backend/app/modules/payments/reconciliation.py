import asyncio
from contextlib import suppress
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.modules.payments import refunds
from app.modules.payments.models import Payment, Refund
from app.modules.payments.service import synchronize_system


class Reconciler:
    def __init__(self, database, adapter):
        self.database = database
        self.adapter = adapter
        self.settings = adapter.settings
        self.stop = asyncio.Event()

    def reconcile_one(self, *, refund=False):
        model, status = (Refund, "processing") if refund else (Payment, "pending")
        with self.database.sessions.begin() as session:
            now = session.scalar(select(func.clock_timestamp()))
            row = session.scalar(
                select(model)
                .where(model.status == status, model.next_reconcile_at <= now)
                .order_by(model.next_reconcile_at, model.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return False
            row.next_reconcile_at = now + timedelta(
                seconds=max(
                    self.settings.payment_reconciliation_interval_seconds,
                    self.settings.payment_timeout_seconds * 4 + 1,
                )
            )
            identity = row.id
        with self.database.sessions() as session:
            (refunds.synchronize_system if refund else synchronize_system)(
                session, identity, self.adapter
            )
        return True

    async def run(self):
        while not self.stop.is_set():
            try:
                for _ in range(self.settings.payment_reconciliation_batch_size):
                    if self.stop.is_set():
                        break
                    payment = await asyncio.to_thread(self.reconcile_one)
                    refund = await asyncio.to_thread(self.reconcile_one, refund=True)
                    if not payment and not refund:
                        break
            except SQLAlchemyError:
                # The persistent schedule permits recovery after database downtime.
                pass
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self.stop.wait(), timeout=self.settings.payment_reconciliation_interval_seconds
                )
