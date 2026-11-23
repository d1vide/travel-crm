from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RequestStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    OFFER_PREPARED = "offer_prepared"
    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TravelRequest(Base):
    __tablename__ = "requests"
    __table_args__ = (
        UniqueConstraint("id", "client_id", name="uq_requests_id_client"),
        CheckConstraint("ends_on >= starts_on", name="valid_dates"),
        CheckConstraint("tourist_count > 0", name="positive_tourist_count"),
        CheckConstraint("budget >= 0", name="nonnegative_budget"),
        CheckConstraint("version > 0", name="positive_version"),
        Index("ix_requests_client_id", "client_id"),
        Index("ix_requests_manager_status_created", "manager_id", "status", "created_at"),
        Index("ix_requests_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"))
    manager_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    destination: Mapped[str] = mapped_column(Text)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    tourist_count: Mapped[int] = mapped_column(Integer)
    budget: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    wishes: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[RequestStatus] = mapped_column(
        Enum(
            RequestStatus,
            values_callable=lambda statuses: [status.value for status in statuses],
            native_enum=False,
            create_constraint=True,
            name="request_status",
        ),
        default=RequestStatus.NEW,
        server_default="new",
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.clock_timestamp()
    )
