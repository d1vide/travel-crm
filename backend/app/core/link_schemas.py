from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field

from app.core.schemas import Dto


class PublicLinkInfo(Dto):
    id: UUID
    purpose: Literal["selection", "tourists"]
    expires_at: datetime
    is_active: bool


class PublicLink(Dto):
    id: UUID
    purpose: Literal["selection", "tourists"]
    url: AnyHttpUrl = Field(repr=False)
    expires_at: datetime
