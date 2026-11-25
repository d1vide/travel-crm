from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.core.database import DbSession
from app.core.errors import Error
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.notifications import service
from app.modules.notifications.schemas import Notification, NotificationPage, NotificationQuery

Staff = Annotated[User, Depends(require_roles(Role.MANAGER, Role.HEAD))]


def privacy(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    tags=["notifications"],
    dependencies=[Depends(privacy)],
    responses={code: {"model": Error} for code in (401, 403, 404, 422, 503)},
)


@router.get(
    "/api/notifications", response_model=NotificationPage, operation_id="list_notifications"
)
def list_notifications(
    actor: Staff, session: DbSession, query: Annotated[NotificationQuery, Query()]
):
    return service.list_notifications(session, actor, query)


@router.post(
    "/api/notifications/{notification_id}/read",
    response_model=Notification,
    operation_id="read_notification",
)
def mark_read(notification_id: UUID, actor: Staff, session: DbSession):
    return service.mark_read(session, actor, notification_id)
