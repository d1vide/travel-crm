from uuid import UUID

from sqlalchemy import exists, false, select

from app.modules.auth.models import Role
from app.modules.requests.models import TravelRequest


def client_has_requests(client_id):
    return exists(
        select(TravelRequest.id)
        .where(TravelRequest.client_id == client_id)
        .correlate_except(TravelRequest)
    )


def client_has_manager(client_id, manager_id: UUID):
    return exists(
        select(TravelRequest.id)
        .where(TravelRequest.client_id == client_id, TravelRequest.manager_id == manager_id)
        .correlate_except(TravelRequest)
    )


def request_is_visible(request_id, actor):
    if actor.role not in (Role.MANAGER, Role.HEAD):
        return false()
    return exists(
        select(TravelRequest.id)
        .where(
            TravelRequest.id == request_id,
            True if actor.role == Role.HEAD else TravelRequest.manager_id == actor.id,
        )
        .correlate_except(TravelRequest)
    )
