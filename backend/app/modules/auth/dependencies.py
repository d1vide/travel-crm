from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import DbSession
from app.core.errors import ApiError
from app.modules.auth.models import Role, User
from app.modules.auth.security import token_subject

bearer = HTTPBearer(auto_error=False, scheme_name="BearerAuth")


def get_current_user(
    request: Request,
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise ApiError(401, "unauthorized", "Требуется вход в систему")
    user = session.get(User, token_subject(credentials.credentials, request.app.state.settings))
    if user is None or not user.is_active:
        raise ApiError(401, "unauthorized", "Сотрудник недоступен или сессия отозвана")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role):
    def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ApiError(403, "forbidden", "Недостаточно прав для этого действия")
        return user

    dependency.allowed_roles = tuple(role.value for role in roles)
    return dependency


def require_same_origin(request: Request):
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (
        origin is not None and origin not in request.app.state.settings.allowed_origins
    ):
        raise ApiError(403, "forbidden", "Недопустимый источник запроса")
