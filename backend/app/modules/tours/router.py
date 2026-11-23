from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.database import DbSession
from app.core.errors import Error
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role
from app.modules.tours import service
from app.modules.tours.schemas import TourOffer, TourOfferPage, TourQuery

router = APIRouter(
    prefix="/api/tours",
    tags=["tours"],
    dependencies=[Depends(require_roles(Role.MANAGER, Role.HEAD))],
    responses={code: {"model": Error} for code in (401, 403, 404, 422, 503)},
)


@router.get("", response_model=TourOfferPage, operation_id="list_tours")
def list_tours(session: DbSession, query: Annotated[TourQuery, Query()]):
    return service.list_tours(session, query)


@router.get("/{tour_id}", response_model=TourOffer, operation_id="get_tour")
def get_tour(tour_id: UUID, session: DbSession):
    return service.get_tour(session, tour_id)
