import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, SecretStr, TypeAdapter, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    database_schema: str = "public"
    jwt_secret_key: SecretStr
    jwt_issuer: str = "travel-crm"
    jwt_audience: str = "travel-crm-web"
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=7, ge=1, le=30)
    cookie_secure: bool = True
    seed_demo: bool = False
    demo_password: SecretStr | None = None
    backend_port: int = Field(default=8000, ge=1, le=65535)
    backend_host: str = "127.0.0.1"
    public_app_url: str = "http://localhost:8080"
    payment_stub_url: str = "http://127.0.0.1:8010"
    payment_stub_key: SecretStr | None = None
    payment_timeout_seconds: float = Field(default=1.0, gt=0, le=30)
    allowed_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value):
        return (
            [item.strip().rstrip("/") for item in value.split(",") if item.strip()]
            if isinstance(value, str)
            else value
        )

    @field_validator("database_schema")
    @classmethod
    def validate_schema(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value):
            raise ValueError("database_schema must be a PostgreSQL identifier")
        return value

    @field_validator("payment_stub_key")
    @classmethod
    def valid_payment_key(cls, value):
        if value is not None and (
            len(value.get_secret_value()) < 32
            or value.get_secret_value().lower().startswith(("replace", "change", "example"))
        ):
            raise ValueError("Generate a payment shared key of at least 32 characters")
        return value

    @field_validator("public_app_url", "payment_stub_url")
    @classmethod
    def public_origin(cls, value):
        from urllib.parse import urlsplit

        value = str(TypeAdapter(AnyHttpUrl).validate_python(value))
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "PUBLIC_APP_URL must be an HTTP(S) origin without credentials or a path"
            )
        _ = parsed.port
        return value.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def validate_database(cls, value: SecretStr) -> SecretStr:
        if make_url(value.get_secret_value()).drivername != "postgresql+psycopg":
            raise ValueError("Use a postgresql+psycopg database URL")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret.encode()) < 32 or secret.lower().startswith(("replace", "change", "example")):
            raise ValueError("Generate a JWT secret of at least 32 bytes")
        return value

    @model_validator(mode="after")
    def validate_environment(self):
        if self.app_env == "production" and (not self.cookie_secure or self.seed_demo):
            raise ValueError("Production requires secure cookies and disabled demo seeding")
        if self.seed_demo and (
            self.demo_password is None or len(self.demo_password.get_secret_value()) < 12
        ):
            raise ValueError("Demo seeding requires DEMO_PASSWORD of at least 12 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
