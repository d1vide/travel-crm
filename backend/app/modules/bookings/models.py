from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BookingStatus(StrEnum):
    PENDING = "pending_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLED = "cancelled"


ACTIVE_STATUSES = (
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.CANCELLATION_REQUESTED,
)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("id", "request_id", name="uq_bookings_id_request"),
        ForeignKeyConstraint(
            ["selection_item_id", "request_id"],
            ["selection_items.id", "selection_items.request_id"],
            name="fk_bookings_item_request",
            ondelete="RESTRICT",
        ),
        Index("ix_bookings_request_created", "request_id", "created_at", "id"),
        Index(
            "uq_bookings_active_request",
            "request_id",
            unique=True,
            postgresql_where=text(
                "status IN ('pending_confirmation', 'confirmed', 'cancellation_requested')"
            ),
        ),
        CheckConstraint(
            "status IN ('pending_confirmation', 'confirmed', 'rejected', 'cancellation_requested', 'cancelled')",
            name="status",
        ),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("total_amount >= 0", name="nonnegative_amount"),
        CheckConstraint("currency = 'RUB'", name="currency"),
        CheckConstraint(
            "jsonb_typeof(offer_snapshot) = 'object' AND offer_snapshot ? 'price' AND offer_snapshot ? 'currency'",
            name="snapshot_object",
        ),
        CheckConstraint(
            "COALESCE(total_amount = (offer_snapshot->>'price')::numeric AND offer_snapshot->>'currency' = currency, false)",
            name="snapshot_price",
        ),
        CheckConstraint(
            "(status = 'rejected') = (rejection_reason IS NOT NULL)", name="rejection_reason"
        ),
        CheckConstraint(
            "rejection_reason IS NULL OR btrim(rejection_reason) <> ''", name="nonblank_rejection"
        ),
        CheckConstraint(
            "supplier_booking_number IS NULL OR btrim(supplier_booking_number) <> ''",
            name="nonblank_supplier_number",
        ),
        CheckConstraint(
            "(status IN ('pending_confirmation', 'rejected') AND supplier_booking_number IS NULL AND confirmed_at IS NULL) OR (status IN ('confirmed', 'cancellation_requested', 'cancelled') AND supplier_booking_number IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="confirmation_fields",
        ),
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)", name="cancellation_time"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column()
    selection_item_id: Mapped[UUID] = mapped_column()
    offer_snapshot: Mapped[dict] = mapped_column(JSONB)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[str] = mapped_column(String(32), default=BookingStatus.PENDING)
    supplier_booking_number: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    cancellation_response: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
    )


class BookingTourist(Base):
    __tablename__ = "booking_tourists"
    __table_args__ = (
        UniqueConstraint("booking_id", "tourist_id", name="uq_booking_tourists_tourist"),
        UniqueConstraint("booking_id", "position", name="uq_booking_tourists_position"),
        ForeignKeyConstraint(
            ["booking_id", "request_id"],
            ["bookings.id", "bookings.request_id"],
            name="fk_booking_tourists_booking_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tourist_id", "request_id"],
            ["tourists.id", "tourists.request_id"],
            name="fk_booking_tourists_tourist_request",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position >= 0", name="nonnegative_position"),
        CheckConstraint("jsonb_typeof(tourist_snapshot) = 'object'", name="snapshot_object"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column()
    tourist_id: Mapped[UUID] = mapped_column()
    request_id: Mapped[UUID] = mapped_column()
    position: Mapped[int] = mapped_column(Integer)
    tourist_snapshot: Mapped[dict] = mapped_column(JSONB)
