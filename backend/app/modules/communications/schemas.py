from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictStr, field_validator
from pydantic_core import PydanticCustomError

from app.core.pagination import PageQuery
from app.core.schemas import Dto
from app.core.validation import UtcTimestamp
from app.modules.auth.schemas import UserDto
from app.modules.clients.normalization import checked_text
from app.modules.communications.models import CommunicationChannel


class CommunicationCreate(Dto):
    request_id: UUID | None
    channel: CommunicationChannel
    text: StrictStr = Field(min_length=1)
    occurred_at: UtcTimestamp

    @field_validator("text", mode="before")
    @classmethod
    def valid_text(cls, value):
        return checked_text(value)

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value):
        value = value.strip()
        if not value:
            raise PydanticCustomError("blank_string", "Введите текст записи")
        return value


class CommunicationQuery(PageQuery):
    sort: Literal["-occurred_at"] = "-occurred_at"


class Communication(Dto):
    id: UUID
    client_id: UUID
    request_id: UUID | None
    author_id: UUID
    channel: CommunicationChannel
    text: str = Field(min_length=1)
    occurred_at: datetime
    created_at: datetime
    author: UserDto


class CommunicationPage(Dto):
    items: list[Communication]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
