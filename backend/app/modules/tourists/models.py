from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Tourist(Base):
    __tablename__ = "tourists"
    __table_args__ = (
        Index("ix_tourists_request_position", "request_id", "position"),
        CheckConstraint("btrim(full_name) <> ''", name="nonblank_name"),
        CheckConstraint("btrim(document_number) <> ''", name="nonblank_document"),
        CheckConstraint(
            "document_type IN ('passport', 'international_passport')", name="document_type"
        ),
        CheckConstraint(
            "document_type <> 'international_passport' OR document_expires_on IS NOT NULL",
            name="international_expiry",
        ),
        CheckConstraint(
            "birth_date <= (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Moscow')::date",
            name="birth_not_future",
        ),
        CheckConstraint("position >= 0", name="nonnegative_position"),
        CheckConstraint("version > 0", name="positive_version"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(ForeignKey("requests.id", ondelete="RESTRICT"))
    full_name: Mapped[str] = mapped_column(Text)
    birth_date: Mapped[date] = mapped_column(Date)
    document_type: Mapped[str] = mapped_column(Text)
    document_number: Mapped[str] = mapped_column(Text)
    document_expires_on: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    position: Mapped[int] = mapped_column(Integer)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.clock_timestamp()
    )
