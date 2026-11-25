import asyncio
from contextlib import suppress
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.modules.payments.models import Payment
from app.modules.payments.service import synchronize_system


class Reconciler:
    def __init__(self, database, adapter):
        self.database = database
        self.adapter = adapter
        self.settings = adapter.settings
        self.stop = asyncio.Event()

    def reconcile_one(self):
        with self.database.sessions.begin() as session:
            now = session.scalar(select(func.clock_timestamp()))
            row = session.scalar(
                select(Payment)
                .where(Payment.status == "pending", Payment.next_reconcile_at <= now)
                .order_by(Payment.next_reconcile_at, Payment.id)
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
            synchronize_system(session, identity, self.adapter)
        return True

    async def run(self):
        while not self.stop.is_set():
            try:
                for _ in range(self.settings.payment_reconciliation_batch_size):
                    if self.stop.is_set() or not await asyncio.to_thread(self.reconcile_one):
                        break
            except SQLAlchemyError:
                # The persistent schedule permits recovery after database downtime.
                pass
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self.stop.wait(), timeout=self.settings.payment_reconciliation_interval_seconds
                )
