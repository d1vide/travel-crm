from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictStr, field_validator

from app.core.schemas import Dto
from app.core.validation import Money
from app.modules.clients.normalization import checked_text
from app.modules.requests.schemas import ExpectedVersion, OfferSnapshot


class ConfirmBooking(ExpectedVersion):
    supplier_booking_number: StrictStr = Field(min_length=1)

    @field_validator("supplier_booking_number", mode="before")
    @classmethod
    def valid_number(cls, value):
        value = checked_text(value)
        return value.strip() if isinstance(value, str) else value


class ConfirmCancellation(ExpectedVersion):
    supplier_response: StrictStr = Field(min_length=1)

    @field_validator("supplier_response", mode="before")
    @classmethod
    def valid_response(cls, value):
        value = checked_text(value)
        return value.strip() if isinstance(value, str) else value


class TouristSnapshot(Dto):
    full_name: str = Field(repr=False)
    birth_date: date = Field(repr=False)
    document_type: Literal["passport", "international_passport"]
    document_number: str = Field(repr=False)
    document_expires_on: date | None = Field(repr=False)


class BookingTourist(Dto):
    tourist_id: UUID
    tourist_snapshot: TouristSnapshot = Field(repr=False)


class Booking(Dto):
    id: UUID
    request_id: UUID
    selection_item_id: UUID
    offer_snapshot: OfferSnapshot
    total_amount: Money
    currency: Literal["RUB"]
    status: Literal[
        "pending_confirmation", "confirmed", "rejected", "cancellation_requested", "cancelled"
    ]
    supplier_booking_number: str | None
    rejection_reason: str | None
    cancellation_reason: str | None
    cancellation_response: str | None
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    paid_amount: Money
    reserved_payment_amount: Money
    remaining_amount: Money
    available_payment_amount: Money
    refunded_amount: Money
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    tourists: list[BookingTourist] = Field(repr=False)
    allowed_actions: list[
        Literal[
            "confirm",
            "reject",
            "request_cancellation",
            "confirm_cancellation",
            "reject_cancellation",
            "create_payment",
        ]
    ]


class BookingPage(Dto):
    items: list[Booking]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
