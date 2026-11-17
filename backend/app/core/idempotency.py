import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Header, Request
from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base
from app.core.errors import ApiError
from app.core.locking import lock_key


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "actor_scope", "operation", "key", name="uq_idempotency_scope_operation_key"
        ),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="valid_request_hash"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_scope: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str] = mapped_column(String(255))
    key: Mapped[UUID] = mapped_column()
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[UUID] = mapped_column()
    result_metadata: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


@dataclass(frozen=True)
class CommandIdentity:
    key: UUID
    payload_hash: str


async def identify_command(
    request: Request,
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> CommandIdentity:
    try:
        raw = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ApiError(422, "validation_error", "Передайте корректный JSON") from error
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return CommandIdentity(key, hashlib.sha256(canonical.encode()).hexdigest())


IdempotentCommand = Annotated[CommandIdentity, Depends(identify_command)]


def find_previous(session: Session, actor_scope: str, operation: str, command: CommandIdentity):
    lock_key(session, f"idempotency:{actor_scope}:{operation}:{command.key}")
    return session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_scope == actor_scope,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == command.key,
        )
    )


def check_payload(record: IdempotencyRecord, command: CommandIdentity):
    if record.request_hash != command.payload_hash:
        raise ApiError(409, "idempotency_conflict", "Этот ключ уже использован для другого запроса")


def remember(
    session: Session,
    actor_scope: str,
    operation: str,
    command: CommandIdentity,
    *,
    resource_type: str,
    resource_id: UUID,
):
    session.add(
        IdempotencyRecord(
            actor_scope=actor_scope,
            operation=operation,
            key=command.key,
            request_hash=command.payload_hash,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    )
