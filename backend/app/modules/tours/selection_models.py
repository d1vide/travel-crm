from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Selection(Base):
    __tablename__ = "selections"
    __table_args__ = (
        UniqueConstraint("id", "request_id", name="uq_selections_id_request"),
        Index("ix_selections_request_created", "request_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(ForeignKey("requests.id", ondelete="RESTRICT"))
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class SelectionItem(Base):
    __tablename__ = "selection_items"
    __table_args__ = (
        UniqueConstraint("selection_id", "tour_offer_id", name="uq_selection_items_offer"),
        UniqueConstraint("selection_id", "position", name="uq_selection_items_position"),
        UniqueConstraint("id", "request_id", name="uq_selection_items_id_request"),
        ForeignKeyConstraint(
            ["selection_id", "request_id"],
            ["selections.id", "selections.request_id"],
            name="fk_selection_items_selection_request",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position >= 0", name="nonnegative_position"),
        CheckConstraint("jsonb_typeof(offer_snapshot) = 'object'", name="snapshot_object"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    selection_id: Mapped[UUID] = mapped_column()
    request_id: Mapped[UUID] = mapped_column()
    tour_offer_id: Mapped[UUID] = mapped_column(ForeignKey("tour_offers.id", ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(Integer)
    offer_snapshot: Mapped[dict] = mapped_column(JSONB)
