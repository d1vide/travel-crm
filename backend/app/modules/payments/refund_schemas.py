from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.core.pagination import PageQuery
from app.core.schemas import Dto
from app.core.validation import Money


class RefundCreate(Dto):
    amount: Money = Field(json_schema_extra={"not": {"const": "0.00"}})
    currency: Literal["RUB"]

    @field_validator("amount")
    @classmethod
    def positive(cls, value):
        if value == "0.00":
            raise ValueError("Сумма должна быть положительной")
        return value


class Refund(Dto):
    id: UUID
    payment_id: UUID
    amount: Money
    currency: Literal["RUB"]
    status: Literal["processing", "succeeded", "failed"]
    external_operation_id: str | None
    failure_reason: str | None
    succeeded_at: datetime | None
    created_at: datetime
    booking_id: UUID
    request_id: UUID
    pending_reason: str | None
    can_open_request: bool
    allowed_actions: list[Literal["reconcile"]]


class RefundPage(Dto):
    items: list[Refund]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class RefundQuery(PageQuery):
    request_id: UUID | None = None
    booking_id: UUID | None = None
    payment_id: UUID | None = None
    status: Literal["processing", "succeeded", "failed"] | None = None
    sort: Literal["-created_at", "created_at"] = "-created_at"
