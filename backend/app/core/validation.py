import re
from datetime import date, datetime
from typing import Annotated

from pydantic import BeforeValidator, Field, StrictStr
from pydantic_core import PydanticCustomError


def calendar_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise PydanticCustomError("calendar_date", "Передайте дату YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise PydanticCustomError("calendar_date", "Передайте дату YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise PydanticCustomError("calendar_date", "Передайте дату YYYY-MM-DD")
    return value


CalendarDate = Annotated[date, BeforeValidator(calendar_date)]
Money = Annotated[StrictStr, Field(pattern=r"^(0|[1-9][0-9]{0,11})\.[0-9]{2}$")]


def utc_timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value
    ):
        raise PydanticCustomError("utc_timestamp", "Передайте время UTC с Z")
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise PydanticCustomError("utc_timestamp", "Передайте время UTC с Z") from error
    return value


UtcTimestamp = Annotated[datetime, BeforeValidator(utc_timestamp)]
