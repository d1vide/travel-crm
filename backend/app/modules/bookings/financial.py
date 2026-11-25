from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field
from sqlalchemy import func, select

from app.core.database import DbSession
from app.core.errors import ApiError, Error
from app.core.pagination import HistoryQuery
from app.core.schemas import Dto
from app.core.validation import Money
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.payments.views import totals
from app.modules.requests.models import TravelRequest


class FinancialBooking(Dto):
    id: UUID
    request_id: UUID
    status: BookingStatus
    total_amount: Money
    currency: Literal["RUB"]
    paid_amount: Money
    reserved_payment_amount: Money
    remaining_amount: Money
    refunded_amount: Money
    can_open_request: bool
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime


class FinancialBookingPage(Dto):
    items: list[FinancialBooking]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class FinancialQuery(HistoryQuery):
    request_id: UUID | None = None
    status: BookingStatus | None = None


Finance = Annotated[User, Depends(require_roles(Role.HEAD, Role.ACCOUNTANT))]
router = APIRouter(
    tags=["financial"], responses={code: {"model": Error} for code in (401, 403, 404, 422, 503)}
)


@router.get(
    "/api/financial-bookings",
    response_model=FinancialBookingPage,
    operation_id="list_financial_bookings",
)
def list_financial(
    actor: Finance,
    session: DbSession,
    query: Annotated[FinancialQuery, Query()],
    response: Response,
):
    response.headers["Cache-Control"] = "no-store"
    conditions = []
    if query.request_id is not None:
        if session.get(TravelRequest, query.request_id) is None:
            raise ApiError(404, "not_found", "Заявка не найдена")
        conditions.append(Booking.request_id == query.request_id)
    if query.status is not None:
        conditions.append(Booking.status == query.status)
    count = session.scalar(select(func.count()).select_from(Booking).where(*conditions))
    rows = session.scalars(
        select(Booking)
        .where(*conditions)
        .order_by(Booking.created_at.desc(), Booking.id.desc())
        .offset(query.offset)
        .limit(query.page_size)
    ).all()
    money = totals(session, [row.id for row in rows])
    return FinancialBookingPage(
        items=[
            FinancialBooking(
                id=row.id,
                request_id=row.request_id,
                status=row.status,
                total_amount=f"{row.total_amount:.2f}",
                currency=row.currency,
                paid_amount=f"{money.get(row.id, (Decimal(0), Decimal(0)))[0]:.2f}",
                reserved_payment_amount=f"{money.get(row.id, (Decimal(0), Decimal(0)))[1]:.2f}",
                remaining_amount=f"{row.total_amount - money.get(row.id, (Decimal(0), Decimal(0)))[0]:.2f}",
                refunded_amount="0.00",
                can_open_request=actor.role == Role.HEAD,
                confirmed_at=row.confirmed_at,
                cancelled_at=row.cancelled_at,
                created_at=row.created_at,
            )
            for row in rows
        ],
        page=query.page,
        page_size=query.page_size,
        total=count,
    )
