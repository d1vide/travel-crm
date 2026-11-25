from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.core.pagination import PageQuery
from app.core.schemas import Dto
from app.core.validation import Money
from app.modules.requests.schemas import ExpectedVersion


class PaymentCreate(ExpectedVersion):
    amount: Money
    currency: Literal["RUB"]

    @field_validator("amount")
    @classmethod
    def positive(cls, value):
        if value == "0.00":
            raise ValueError("Сумма должна быть положительной")
        return value


class Payment(Dto):
    id: UUID
    booking_id: UUID
    amount: Money
    currency: Literal["RUB"]
    status: Literal["pending", "succeeded", "failed"]
    external_operation_id: str | None
    payment_url: str | None = Field(repr=False)
    failure_reason: str | None
    succeeded_at: datetime | None
    created_at: datetime
    request_id: UUID
    booking_status: Literal[
        "pending_confirmation", "confirmed", "rejected", "cancellation_requested", "cancelled"
    ]
    pending_reason: str | None
    refunded_amount: Money
    reserved_refund_amount: Money
    available_refund_amount: Money
    can_open_request: bool
    allowed_actions: list[Literal["reconcile", "create_refund"]]


class PaymentPage(Dto):
    items: list[Payment]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class PaymentQuery(PageQuery):
    request_id: UUID | None = None
    booking_id: UUID | None = None
    status: Literal["pending", "succeeded", "failed"] | None = None
    sort: Literal["-created_at", "created_at"] = "-created_at"
