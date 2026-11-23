from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditRecord(Base):
    __tablename__ = "audit_records"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('request', 'booking', 'payment', 'refund')", name="entity_type"
        ),
        CheckConstraint("source IN ('staff', 'payment_service', 'system')", name="source"),
        CheckConstraint("jsonb_typeof(changes) = 'array'", name="changes_array"),
        Index("ix_audit_records_request_created", "request_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(ForeignKey("requests.id", ondelete="RESTRICT"))
    entity_id: Mapped[UUID] = mapped_column()
    entity_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    source: Mapped[str] = mapped_column(String(24))
    action: Mapped[str] = mapped_column(String(64))
    changes: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def record_request_change(session, request, actor, field, old_value, new_value, action):
    if field not in {"manager_id", "request_status"}:
        raise ValueError("Unsupported request audit field")
    session.add(
        AuditRecord(
            request_id=request.id,
            entity_id=request.id,
            entity_type="request",
            actor_id=actor.id,
            source="staff",
            action=action,
            changes=[
                {
                    "field": field,
                    "old_value": str(old_value) if old_value is not None else None,
                    "new_value": str(new_value) if new_value is not None else None,
                }
            ],
        )
    )
