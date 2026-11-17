from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        CheckConstraint("length(trim(full_name)) > 0", name="full_name_not_blank"),
        CheckConstraint(
            "phone_normalized IS NOT NULL OR email_normalized IS NOT NULL", name="contact_required"
        ),
        CheckConstraint("(phone IS NULL) = (phone_normalized IS NULL)", name="phone_pair"),
        CheckConstraint("(email IS NULL) = (email_normalized IS NULL)", name="email_pair"),
        CheckConstraint(
            "phone_normalized IS NULL OR phone_normalized ~ '^\\+[0-9]{7,15}$'", name="phone_format"
        ),
        CheckConstraint(
            "email_normalized IS NULL OR length(trim(email_normalized)) > 0", name="email_not_blank"
        ),
        CheckConstraint("client_number > 0", name="positive_number"),
        CheckConstraint("version > 0", name="positive_version"),
        Index("ix_clients_phone_normalized", "phone_normalized"),
        Index("ix_clients_email_normalized", "email_normalized"),
        Index("ix_clients_created_by_id", "created_by_id"),
        Index(
            "ix_clients_full_name_trgm",
            "full_name_normalized",
            postgresql_using="gin",
            postgresql_ops={"full_name_normalized": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_number: Mapped[int] = mapped_column(Integer, Identity(start=1), unique=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    full_name: Mapped[str] = mapped_column(Text)
    full_name_normalized: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone_normalized: Mapped[str | None] = mapped_column(String(16))
    email_normalized: Mapped[str | None] = mapped_column(Text)
    preferences: Mapped[str] = mapped_column(Text, default="", server_default="")
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.clock_timestamp()
    )
