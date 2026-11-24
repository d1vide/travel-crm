from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.core.database import DbSession
from app.core.errors import Error
from app.core.idempotency import IdempotentCommand
from app.core.pagination import HistoryQuery
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.bookings import service
from app.modules.bookings.schemas import Booking, BookingPage, ConfirmBooking
from app.modules.requests.schemas import ExpectedVersion, ReasonCommand

Staff = Annotated[User, Depends(require_roles(Role.MANAGER, Role.HEAD))]


def privacy(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


router = APIRouter(
    tags=["bookings"],
    dependencies=[Depends(privacy)],
    responses={code: {"model": Error} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/api/requests/{request_id}/bookings",
    response_model=BookingPage,
    operation_id="list_request_bookings",
)
def list_bookings(
    request_id: UUID, actor: Staff, session: DbSession, query: Annotated[HistoryQuery, Query()]
):
    return service.list_bookings(session, actor, request_id, query)


@router.post(
    "/api/requests/{request_id}/bookings",
    response_model=Booking,
    status_code=201,
    operation_id="create_booking",
)
def create_booking(
    request_id: UUID,
    actor: Staff,
    session: DbSession,
    body: ExpectedVersion,
    command: IdempotentCommand,
):
    return service.create_booking(session, actor, request_id, body, command)


@router.get("/api/bookings/{booking_id}", response_model=Booking, operation_id="get_booking")
def get_booking(booking_id: UUID, actor: Staff, session: DbSession):
    return service.get_booking(session, actor, booking_id)


@router.post(
    "/api/bookings/{booking_id}/actions/confirm",
    response_model=Booking,
    operation_id="confirm_booking",
)
def confirm_booking(
    booking_id: UUID,
    actor: Staff,
    session: DbSession,
    body: ConfirmBooking,
    command: IdempotentCommand,
):
    return service.act(session, actor, booking_id, body, command, "confirm")


@router.post(
    "/api/bookings/{booking_id}/actions/reject",
    response_model=Booking,
    operation_id="reject_booking",
)
def reject_booking(
    booking_id: UUID,
    actor: Staff,
    session: DbSession,
    body: ReasonCommand,
    command: IdempotentCommand,
):
    return service.act(session, actor, booking_id, body, command, "reject")
