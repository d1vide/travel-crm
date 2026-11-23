from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import func, select

from app.core.database import DbSession
from app.core.errors import ApiError, Error
from app.core.pagination import PageQuery
from app.core.schemas import Dto
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.auth.schemas import UserDto


class AssigneeQuery(PageQuery):
    sort: Literal["full_name"] = "full_name"


class UserPage(Dto):
    items: list[UserDto]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


def user_briefs(session, identities):
    return {
        user.id: UserDto.model_validate(user)
        for user in session.scalars(select(User).where(User.id.in_(identities)))
    }


def active_assignee(session, identity: UUID) -> User:
    user = session.scalar(
        select(User)
        .where(User.id == identity)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if user is None or not user.is_active or user.role not in (Role.MANAGER, Role.HEAD):
        raise ApiError(422, "validation_error", "Выберите активного менеджера или руководителя")
    return user


router = APIRouter(
    tags=["users"],
    responses={
        401: {"model": Error},
        403: {"model": Error},
        422: {"model": Error},
        503: {"model": Error},
    },
)


@router.get(
    "/api/users",
    response_model=UserPage,
    operation_id="list_assignees",
    dependencies=[Depends(require_roles(Role.HEAD))],
)
def list_assignees(session: DbSession, query: Annotated[AssigneeQuery, Query()]):
    conditions = (User.is_active.is_(True), User.role.in_([Role.MANAGER, Role.HEAD]))
    total = session.scalar(select(func.count()).select_from(User).where(*conditions))
    users = session.scalars(
        select(User)
        .where(*conditions)
        .order_by(func.lower(User.full_name), User.id)
        .offset(query.offset)
        .limit(query.page_size)
    )
    return UserPage(
        items=[UserDto.model_validate(user) for user in users],
        page=query.page,
        page_size=query.page_size,
        total=total,
    )
