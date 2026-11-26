from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Date, DateTime, cast, func, literal, select, text

from app.core.database import DbSession
from app.core.errors import Error
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.bookings.models import Booking
from app.modules.payments.models import Payment, Refund
from app.modules.reports.schemas import Period, Report
from app.modules.requests.models import TravelRequest

Head = Annotated[User, Depends(require_roles(Role.HEAD))]
router = APIRouter(
    tags=["reports"], responses={code: {"model": Error} for code in (401, 403, 422, 503)}
)


@router.get("/api/reports/summary", response_model=Report, operation_id="get_summary_report")
def summary(
    _actor: Head, session: DbSession, period: Annotated[Period, Query()], response: Response
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    # PostgreSQL supplies Moscow's calendar rules on every supported host.
    start = func.timezone("Europe/Moscow", cast(literal(period.date_from, type_=Date), DateTime))
    end = func.timezone(
        "Europe/Moscow",
        cast(literal(period.date_to, type_=Date), DateTime) + text("INTERVAL '1 day'"),
    )

    def metric(model, column, *, amount=False):
        value = func.coalesce(func.sum(model.amount), 0) if amount else func.count()
        conditions = [column >= start, column < end]
        if amount:
            conditions.append(model.status == "succeeded")
        return select(value).select_from(model).where(*conditions).scalar_subquery()

    # Separate aggregates avoid multiplying rows and share one statement snapshot.
    requests, bookings, paid, refunded = session.execute(
        select(
            metric(TravelRequest, TravelRequest.created_at),
            metric(Booking, Booking.confirmed_at),
            metric(Payment, Payment.succeeded_at, amount=True),
            metric(Refund, Refund.succeeded_at, amount=True),
        )
    ).one()
    return Report(
        date_from=period.date_from,
        date_to=period.date_to,
        requests_created=requests,
        bookings_confirmed=bookings,
        payments_succeeded_amount=f"{paid:.2f}",
        refunds_succeeded_amount=f"{refunded:.2f}",
    )
