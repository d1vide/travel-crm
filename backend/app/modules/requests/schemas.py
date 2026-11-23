from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictStr, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.core.pagination import PageQuery
from app.core.schemas import Dto
from app.core.validation import CalendarDate, Money
from app.modules.auth.schemas import UserDto
from app.modules.clients.normalization import checked_text
from app.modules.clients.schemas import ClientBrief
from app.modules.requests.models import RequestStatus


class ExpectedVersion(Dto):
    version: int = Field(ge=1, strict=True)


class RequestFields(Dto):
    destination: StrictStr = Field(min_length=1)
    starts_on: CalendarDate
    ends_on: CalendarDate
    tourist_count: int = Field(ge=1, le=2_147_483_647, strict=True)
    budget: Money
    wishes: StrictStr

    @field_validator("destination", "wishes", mode="before")
    @classmethod
    def valid_text(cls, value):
        return checked_text(value)

    @field_validator("destination")
    @classmethod
    def nonblank_destination(cls, value):
        value = value.strip()
        if not value:
            raise PydanticCustomError("blank_string", "Укажите направление")
        return value

    @field_validator("ends_on")
    @classmethod
    def date_range(cls, value, info: ValidationInfo):
        if info.data.get("starts_on") is not None and value < info.data["starts_on"]:
            raise PydanticCustomError("date_order", "Дата окончания раньше начала")
        return value


class RequestCreate(RequestFields):
    client_id: UUID
    manager_id: UUID | None


class RequestUpdate(RequestFields, ExpectedVersion):
    pass


class AssignRequest(ExpectedVersion):
    manager_id: UUID


class ReasonCommand(ExpectedVersion):
    reason: StrictStr = Field(min_length=1)

    @field_validator("reason", mode="before")
    @classmethod
    def reason_text(cls, value):
        return checked_text(value)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value):
        value = value.strip()
        if not value:
            raise PydanticCustomError("blank_string", "Укажите причину")
        return value


class RequestQuery(PageQuery):
    status: RequestStatus | None = None
    manager_id: UUID | None = None
    client_id: UUID | None = None
    sort: Literal["-created_at", "created_at", "starts_on"] = "-created_at"


class OfferSnapshot(Dto):
    title: str
    destination: str
    starts_on: date
    ends_on: date
    tourist_count: int = Field(ge=1)
    supplier: str
    services: list[str]
    price: Money
    currency: Literal["RUB"]


class BookingSummary(Dto):
    id: UUID
    status: Literal[
        "pending_confirmation", "confirmed", "rejected", "cancellation_requested", "cancelled"
    ]
    total_amount: Money
    currency: Literal["RUB"]
    paid_amount: Money
    remaining_amount: Money


class PublicLinkInfo(Dto):
    id: UUID
    purpose: Literal["selection", "tourist_form"]
    expires_at: datetime
    is_active: bool


class Request(Dto):
    id: UUID
    client_id: UUID
    manager_id: UUID
    destination: str
    starts_on: date
    ends_on: date
    tourist_count: int = Field(ge=1)
    budget: Money
    wishes: str
    status: RequestStatus
    selected_selection_item_id: UUID | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    client: ClientBrief
    manager: UserDto
    selected_selection_id: UUID | None
    selected_offer: OfferSnapshot | None
    active_booking: BookingSummary | None
    tourists_received: int = Field(ge=0)
    tourist_form_editable: bool
    tourist_link: PublicLinkInfo | None
    cancellation_reason: str | None
    allowed_actions: list[
        Literal[
            "update",
            "start_work",
            "return_to_work",
            "prepare_selection",
            "select_tour",
            "issue_tourist_link",
            "edit_tourists",
            "create_booking",
            "reassign",
            "cancel",
            "complete",
            "resume",
        ]
    ]


class RequestPage(Dto):
    items: list[Request]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class AuditChange(Dto):
    field: Literal[
        "manager_id",
        "request_status",
        "booking_status",
        "payment_status",
        "refund_status",
        "amount",
    ]
    old_value: str | None
    new_value: str | None


class AuditRecord(Dto):
    id: UUID
    request_id: UUID
    entity_id: UUID
    entity_type: Literal["request", "booking", "payment", "refund"]
    actor: UserDto | None
    source: Literal["staff", "payment_service", "system"]
    action: str
    changes: list[AuditChange]
    created_at: datetime


class AuditRecordPage(Dto):
    items: list[AuditRecord]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
