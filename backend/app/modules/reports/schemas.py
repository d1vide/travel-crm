from datetime import date
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.core.schemas import Dto
from app.core.validation import CalendarDate, Money


class Period(Dto):
    date_from: CalendarDate
    date_to: CalendarDate

    @field_validator("date_to")
    @classmethod
    def ordered(cls, value, info: ValidationInfo):
        if info.data.get("date_from") is not None and value < info.data["date_from"]:
            raise PydanticCustomError("date_order", "Дата окончания раньше начала")
        return value


class Report(Dto):
    date_from: date
    date_to: date
    timezone: Literal["Europe/Moscow"] = "Europe/Moscow"
    currency: Literal["RUB"] = "RUB"
    requests_created: int = Field(ge=0)
    bookings_confirmed: int = Field(ge=0)
    payments_succeeded_amount: Money
    refunds_succeeded_amount: Money
