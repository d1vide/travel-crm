from uuid import UUID

from sqlalchemy import exists, select

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
