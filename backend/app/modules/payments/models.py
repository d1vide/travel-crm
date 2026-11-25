from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint(
            "provider", "external_operation_id", name="uq_payments_provider_operation"
        ),
        Index("ix_payments_booking_status", "booking_id", "status"),
        Index("ix_payments_created", "created_at", "id"),
        Index(
            "ix_payments_pending_reconcile",
            "next_reconcile_at",
            "id",
            postgresql_where=text("status = 'pending'"),
        ),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("currency = 'RUB'", name="currency"),
        CheckConstraint("status IN ('pending','succeeded','failed')", name="status"),
        CheckConstraint("(status = 'succeeded') = (succeeded_at IS NOT NULL)", name="success_time"),
        CheckConstraint(
            "(status = 'failed') = (failure_reason IS NOT NULL)", name="failure_reason"
        ),
        CheckConstraint("status = 'pending' OR pending_reason IS NULL", name="pending_reason"),
        CheckConstraint(
            "status = 'pending' OR external_operation_id IS NOT NULL", name="terminal_operation"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    provider: Mapped[str] = mapped_column(String(32), default="demo_stub")
    next_reconcile_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    external_operation_id: Mapped[str | None] = mapped_column(String(64))
    payment_url: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    pending_reason: Mapped[str | None] = mapped_column(
        Text, default="Создание операции в платёжном сервисе"
    )
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_conflict: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class PaymentNotification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "recipient_id", "payment_id", "type", name="uq_notifications_recipient_payment_type"
        ),
        CheckConstraint("type = 'payment_succeeded'", name="type"),
        Index("ix_notifications_recipient_created", "recipient_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    payment_id: Mapped[UUID] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(String(32), default="payment_succeeded")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
