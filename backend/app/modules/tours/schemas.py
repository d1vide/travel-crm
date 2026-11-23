from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.core.pagination import PageQuery
from app.core.schemas import Dto
from app.core.validation import CalendarDate, Money
from app.modules.clients.normalization import checked_text


class TourQuery(PageQuery):
    destination: str | None = Field(default=None, min_length=1)
    starts_from: CalendarDate | None = None
    ends_until: CalendarDate | None = None
    tourist_count: int | None = Field(default=None, ge=1, le=2_147_483_647)
    max_price: Money | None = None
    sort: Literal["price", "-price", "starts_on"] = "price"

    @field_validator("destination")
    @classmethod
    def destination_text(cls, value):
        if value is not None:
            checked_text(value)
            value = value.strip()
            if not value:
                raise PydanticCustomError("blank_string", "Введите направление")
        return value

    @field_validator("ends_until")
    @classmethod
    def date_interval(cls, value, info: ValidationInfo):
        if (
            value is not None
            and info.data.get("starts_from") is not None
            and value < info.data["starts_from"]
        ):
            raise PydanticCustomError("date_order", "Дата окончания раньше начала")
        return value


class TourOffer(Dto):
    id: UUID
    title: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    starts_on: date
    ends_on: date
    tourist_count: int = Field(ge=1)
    supplier: str = Field(min_length=1)
    services: list[str]
    price: Money
    currency: Literal["RUB"]
    is_active: bool
    version: int = Field(ge=1)


class TourOfferPage(Dto):
    items: list[TourOffer]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
