import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, String, create_engine
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
        CheckConstraint("amount > 0", name="ck_operations_positive_amount"),
        CheckConstraint("currency = 'RUB'", name="ck_operations_currency"),
        CheckConstraint("status IN ('pending','succeeded','failed')", name="ck_operations_status"),
        CheckConstraint(
            "(status = 'succeeded') = (succeeded_at IS NOT NULL)", name="ck_operations_success_time"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_operation_id: Mapped[UUID] = mapped_column(unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[str] = mapped_column(String(16), default="pending")
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
