from typing import Literal

from pydantic import Field

from app.core.schemas import Dto


class PageQuery(Dto):
    page: int = Field(default=1, ge=1, le=2_147_483_647)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self):
        return (self.page - 1) * self.page_size


class HistoryQuery(PageQuery):
    sort: Literal["-created_at"] = "-created_at"
