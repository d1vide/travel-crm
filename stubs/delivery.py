import asyncio
from contextlib import suppress
from datetime import timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from stubs.protocol import dto
from stubs.store import Operation


class Delivery:
    def __init__(self, settings, sessions):
        self.settings = settings
        self.sessions = sessions
        self.stop = asyncio.Event()

    def deliver_one(self):
        with self.sessions.begin() as session:
            now = session.scalar(select(func.clock_timestamp()))
            row = session.scalar(
                select(Operation)
                .where(
                    Operation.delivery_pending.is_(True),
                    Operation.status.in_(("succeeded", "failed")),
                    Operation.next_delivery_at <= now,
                )
                .order_by(Operation.next_delivery_at, Operation.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return False
            row.next_delivery_at = now + timedelta(
                seconds=max(
                    self.settings.stub_delivery_interval_seconds,
                    self.settings.stub_callback_timeout_seconds * 8 + 1,
                )
            )
            identity, status, payload = row.id, row.status, dto(self.settings, row)
        try:
            with httpx.Client(
                trust_env=False,
                follow_redirects=False,
                timeout=self.settings.stub_callback_timeout_seconds,
                headers={
                    "Authorization": "Bearer " + self.settings.payment_stub_key.get_secret_value()
                },
            ) as client:
                # The repeated delivery exercises the receiver's idempotency.
                for _ in range(2):
                    response = client.post(self.settings.payment_callback_url, json=payload)
                    response.raise_for_status()
        except httpx.HTTPError:
            return True
        with self.sessions.begin() as session:
            row = session.scalar(
                select(Operation).where(Operation.id == identity).with_for_update()
            )
            if row.status == status:
                row.delivery_pending = False
        return True

    async def run(self):
        while not self.stop.is_set():
            try:
                for _ in range(20):
                    if self.stop.is_set() or not await asyncio.to_thread(self.deliver_one):
                        break
            except SQLAlchemyError:
                pass
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self.stop.wait(),
                    timeout=self.settings.stub_delivery_interval_seconds,
                )
