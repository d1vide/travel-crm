from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.core.pagination import HistoryQuery
from app.core.schemas import Dto
from app.core.validation import Money


class Notification(Dto):
    id: UUID
    recipient_id: UUID
    payment_id: UUID
    type: Literal["payment_succeeded"]
    read_at: datetime | None
    created_at: datetime
    request_id: UUID | None
    amount: Money
    currency: Literal["RUB"]
    can_open_request: bool


class NotificationPage(Dto):
    items: list[Notification]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    unread_count: int = Field(ge=0)


class NotificationQuery(HistoryQuery):
    unread_only: bool = False
