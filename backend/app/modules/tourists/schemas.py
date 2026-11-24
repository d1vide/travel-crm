from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictStr, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.core.schemas import Dto
from app.core.validation import CalendarDate
from app.modules.clients.normalization import checked_text


class TouristFields(Dto):
    full_name: StrictStr = Field(min_length=1, repr=False)
    birth_date: CalendarDate = Field(repr=False)
    document_type: Literal["passport", "international_passport"]
    document_number: StrictStr = Field(min_length=1, repr=False)
    document_expires_on: CalendarDate | None = Field(repr=False)

    @field_validator("full_name", "document_number", mode="before")
    @classmethod
    def safe_text(cls, value):
        value = checked_text(value)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise PydanticCustomError("blank_string", "Поле не должно быть пустым")
        return value

    @field_validator("birth_date")
    @classmethod
    def birth_not_future(cls, value):
        if value > datetime.now(timezone(timedelta(hours=3))).date():
            raise PydanticCustomError("birth_not_future", "Дата рождения не может быть в будущем")
        return value

    @field_validator("document_expires_on")
    @classmethod
    def international_expiry(cls, value, info: ValidationInfo):
        if info.data.get("document_type") == "international_passport" and value is None:
            raise PydanticCustomError("passport_expiry", "Укажите срок действия загранпаспорта")
        return value


class TouristSubmissionItem(TouristFields):
    id: UUID | None


class TouristSubmission(Dto):
    request_version: int = Field(ge=1, strict=True)
    tourists: list[TouristSubmissionItem] = Field(min_length=1, repr=False)


class Tourist(Dto):
    id: UUID
    request_id: UUID
    full_name: str = Field(repr=False)
    birth_date: date = Field(repr=False)
    document_type: Literal["passport", "international_passport"]
    document_number: str = Field(repr=False)
    document_expires_on: date | None = Field(repr=False)
    version: int = Field(ge=1)


class PublicTouristForm(Dto):
    tourist_count: int = Field(ge=1)
    request_version: int = Field(ge=1)
    expires_at: datetime
    is_editable: bool
    closed_reason: str | None


class TouristSubmissionResult(Dto):
    accepted_count: int = Field(ge=1)
    request_version: int = Field(ge=1)
