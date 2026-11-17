from sqlalchemy import and_, false, or_, true

from app.modules.auth.models import Role, User
from app.modules.clients.models import Client
from app.modules.requests.access import client_has_manager, client_has_requests


def visible_clients(actor: User):
    if actor.role == Role.HEAD:
        return true()
    if actor.role != Role.MANAGER:
        return false()
    return or_(
        client_has_manager(Client.id, actor.id),
        and_(Client.created_by_id == actor.id, ~client_has_requests(Client.id)),
    )
