from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictStr, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.core.schemas import Dto
from app.modules.clients.normalization import (
    checked_text,
    clean_contact,
    normalize_email,
    normalize_phone,
)


class ClientAction(StrEnum):
    UPDATE = "update"
    CREATE_REQUEST = "create_request"


class Contacts(Dto):
    phone: StrictStr | None
    email: StrictStr | None

    @field_validator("phone", "email", mode="before")
    @classmethod
    def strip_contacts(cls, value):
        return clean_contact(value)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is not None:
            normalize_phone(value)
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        return normalize_email(value) if value is not None else None

    @model_validator(mode="after")
    def require_contact(self):
        if self.phone is None and self.email is None:
            raise PydanticCustomError("contact_required", "Укажите телефон или email")
        return self

    def normalized_contacts(self) -> set[tuple[str, str]]:
        contacts = set()
        if self.phone is not None:
            contacts.add(("phone", normalize_phone(self.phone)))
        if self.email is not None:
            contacts.add(("email", self.email))
        return contacts


class ClientCreate(Contacts):
    full_name: StrictStr = Field(min_length=1)
    preferences: StrictStr
    note: StrictStr
    duplicate_acknowledged: StrictBool

    @field_validator("full_name", "preferences", "note", mode="before")
    @classmethod
    def validate_text(cls, value):
        return checked_text(value)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value):
        cleaned = " ".join(value.split())
        if not cleaned:
            raise PydanticCustomError("blank_string", "Поле не должно быть пустым")
        return cleaned


class ClientUpdate(ClientCreate):
    version: int = Field(ge=1, strict=True)


class Client(Dto):
    id: UUID
    client_number: int = Field(ge=1)
    full_name: str
    phone: str | None
    email: str | None
    preferences: str
    note: str
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    allowed_actions: list[ClientAction]


class ClientBrief(Dto):
    id: UUID
    client_number: int = Field(ge=1)
    full_name: str


class ClientPage(Dto):
    items: list[Client]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class DuplicateCheckResult(Dto):
    matches: list[ClientBrief]
    requires_head_review: bool


class ClientListQuery(Dto):
    q: str | None = Field(default=None, min_length=1)
    page: int = Field(default=1, ge=1, le=2_147_483_647)
    page_size: int = Field(default=20, ge=1, le=100)
    sort: Literal["-created_at", "full_name", "client_number"] = "-created_at"

    @field_validator("q")
    @classmethod
    def clean_query(cls, value):
        if value is None:
            return None
        checked_text(value)
        if not value.strip():
            raise PydanticCustomError("blank_string", "Введите строку поиска")
        return value.strip()


class DuplicateQuery(Contacts):
    phone: StrictStr | None = None
    email: StrictStr | None = None
    exclude_client_id: UUID | None = None
