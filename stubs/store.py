import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import AnyHttpUrl, Field, SecretStr, TypeAdapter, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    create_engine,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
        hide_input_in_errors=True,
    )
    database_url: SecretStr
    stub_schema: str = "payment_stub"
    payment_stub_key: SecretStr = Field(min_length=32)
    public_app_url: str = "http://localhost:8080"
    stub_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    payment_callback_url: str | None = None
    stub_delivery_interval_seconds: float = Field(default=1.0, ge=0.05, le=300)
    stub_callback_timeout_seconds: float = Field(default=1.0, gt=0, le=30)
    stub_refund_outcome: Literal["succeeded", "failed", "timeout"] = "succeeded"

    @field_validator("payment_callback_url")
    @classmethod
    def callback(cls, value):
        if value is None:
            return None
        value = str(TypeAdapter(AnyHttpUrl).validate_python(value))
        parsed = urlsplit(value)
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Callback must be an HTTP(S) URL without credentials, query or fragment"
            )
        return value

    @field_validator("payment_stub_key")
    @classmethod
    def key(cls, value):
        if len(value.get_secret_value()) < 32 or value.get_secret_value().lower().startswith(
            ("replace", "change", "example")
        ):
            raise ValueError("Generate a payment shared key of at least 32 characters")
        return value

    @field_validator("stub_schema")
    @classmethod
    def schema(cls, value):
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value):
            raise ValueError("Invalid schema")
        return value


class Base(DeclarativeBase):
    pass


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (
        Index(
            "ix_operations_delivery",
            "next_delivery_at",
            "id",
            postgresql_where=text("delivery_pending"),
        ),
        CheckConstraint("amount > 0", name="ck_operations_positive_amount"),
        CheckConstraint("currency = 'RUB'", name="ck_operations_currency"),
        CheckConstraint("status IN ('pending','succeeded','failed')", name="ck_operations_status"),
        CheckConstraint(
            "(status = 'succeeded') = (succeeded_at IS NOT NULL)",
            name="ck_operations_success_time",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_operation_id: Mapped[UUID] = mapped_column(unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    simulate_timeout: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    delivery_pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    next_delivery_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefundOperation(Base):
    __tablename__ = "refund_operations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_refund_operations_positive_amount"),
        CheckConstraint("currency = 'RUB'", name="ck_refund_operations_currency"),
        CheckConstraint(
            "status IN ('processing','succeeded','failed')", name="ck_refund_operations_status"
        ),
        CheckConstraint(
            "(status = 'succeeded') = (succeeded_at IS NOT NULL)",
            name="ck_refund_operations_success_time",
        ),
        Index("ix_refund_operations_payment_status", "payment_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_operation_id: Mapped[UUID] = mapped_column(unique=True)
    payment_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[str] = mapped_column(String(16), default="processing")
    simulate_timeout: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def database(settings):
    engine = create_engine(
        settings.database_url.get_secret_value(),
        hide_parameters=True,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 5,
            "options": f"-csearch_path={settings.stub_schema} -ctimezone=UTC",
        },
    )
    return engine, sessionmaker(engine, expire_on_commit=False)
