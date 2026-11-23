from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TourOffer(Base):
    __tablename__ = "tour_offers"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint("length(trim(destination)) > 0", name="destination_not_blank"),
        CheckConstraint(
            "length(trim(destination_normalized)) > 0", name="normalized_destination_not_blank"
        ),
        CheckConstraint("length(trim(supplier)) > 0", name="supplier_not_blank"),
        CheckConstraint("ends_on >= starts_on", name="valid_dates"),
        CheckConstraint("tourist_count > 0", name="positive_tourist_count"),
        CheckConstraint("price >= 0", name="nonnegative_price"),
        CheckConstraint("currency = 'RUB'", name="ruble_currency"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "coalesce(array_ndims(services), 1) = 1 AND array_position(services, NULL) IS NULL AND array_position(services, '') IS NULL",
            name="valid_services",
        ),
        Index(
            "ix_tour_offers_active_filters",
            "tourist_count",
            "starts_on",
            "price",
            postgresql_where=text("is_active"),
        ),
        Index(
            "ix_tour_offers_active_destination",
            "destination_normalized",
            postgresql_using="gin",
            postgresql_ops={"destination_normalized": "gin_trgm_ops"},
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(Text)
    destination: Mapped[str] = mapped_column(Text)
    destination_normalized: Mapped[str] = mapped_column(Text)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    tourist_count: Mapped[int] = mapped_column(Integer)
    supplier: Mapped[str] = mapped_column(Text)
    services: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(Text, default="RUB", server_default="RUB")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.clock_timestamp()
    )
