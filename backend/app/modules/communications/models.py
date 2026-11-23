from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CommunicationChannel(StrEnum):
    PHONE = "phone"
    EMAIL = "email"
    MESSENGER = "messenger"
    OFFICE = "office"
    OTHER = "other"


class Communication(Base):
    __tablename__ = "communications"
    __table_args__ = (
        CheckConstraint("length(trim(text)) > 0", name="text_not_blank"),
        ForeignKeyConstraint(
            ["request_id", "client_id"],
            ["requests.id", "requests.client_id"],
            name="fk_communications_request_client",
            ondelete="RESTRICT",
        ),
        Index("ix_communications_client_occurred", "client_id", "occurred_at", "id"),
        Index("ix_communications_request_occurred", "request_id", "occurred_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"))
    request_id: Mapped[UUID | None] = mapped_column()
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    channel: Mapped[CommunicationChannel] = mapped_column(
        Enum(
            CommunicationChannel,
            values_callable=lambda channels: [channel.value for channel in channels],
            native_enum=False,
            create_constraint=True,
            name="communication_channel",
        )
    )
    text: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
