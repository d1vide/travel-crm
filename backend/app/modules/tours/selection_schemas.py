from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.core.link_schemas import PublicLinkInfo
from app.core.schemas import Dto
from app.modules.requests.schemas import ExpectedVersion, OfferSnapshot


class SelectionCreate(ExpectedVersion):
    tour_offer_ids: list[UUID] = Field(min_length=1)

    @field_validator("tour_offer_ids")
    @classmethod
    def unique_offers(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Туры не должны повторяться")
        return value


class SelectTour(ExpectedVersion):
    selection_item_id: UUID


class SelectionItem(Dto):
    id: UUID
    tour_offer_id: UUID
    position: int = Field(ge=0)
    offer_snapshot: OfferSnapshot


class Selection(Dto):
    id: UUID
    request_id: UUID
    items: list[SelectionItem] = Field(min_length=1)
    created_at: datetime
    public_link: PublicLinkInfo | None


class SelectionPage(Dto):
    items: list[Selection]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class PublicSelectionItem(Dto):
    id: UUID
    offer_snapshot: OfferSnapshot


class PublicSelection(Dto):
    items: list[PublicSelectionItem] = Field(min_length=1)
    expires_at: datetime
