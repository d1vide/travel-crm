from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, Security
from fastapi.security import APIKeyCookie

from app.core.database import DbSession
from app.core.errors import Error
from app.modules.auth.dependencies import CurrentUser, require_same_origin
from app.modules.auth.schemas import AuthResult, LoginInput, UserProfileDto
from app.modules.auth.service import AuthService

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
    responses={
        401: {"model": Error},
        403: {"model": Error},
        422: {"model": Error},
        503: {"model": Error},
    },
)
COOKIE_NAME = "refresh_token"
COOKIE_PATH = "/api/auth"
refresh_cookie = APIKeyCookie(name=COOKIE_NAME, auto_error=False, scheme_name="RefreshCookie")


def set_cookie(request: Request, response: Response, token: str):
    settings = request.app.state.settings
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=COOKIE_PATH,
        max_age=settings.refresh_token_days * 86400,
    )


@router.post(
    "/login",
    response_model=AuthResult,
    operation_id="login",
    dependencies=[Depends(require_same_origin)],
)
def login(body: LoginInput, request: Request, response: Response, session: DbSession):
    result = AuthService(request.app.state.settings).login(session, body.email, body.password)
    set_cookie(request, response, result.refresh)
    response.headers["Cache-Control"] = "no-store"
    return result.body


@router.post(
    "/refresh",
    response_model=AuthResult,
    operation_id="refresh_session",
    dependencies=[Depends(require_same_origin)],
)
def refresh(
    request: Request,
    response: Response,
    session: DbSession,
    raw: Annotated[str | None, Security(refresh_cookie)],
):
    result = AuthService(request.app.state.settings).refresh(session, raw)
    set_cookie(request, response, result.refresh)
    response.headers["Cache-Control"] = "no-store"
    return result.body


@router.post(
    "/logout", status_code=204, operation_id="logout", dependencies=[Depends(require_same_origin)]
)
def logout(request: Request, session: DbSession):
    AuthService(request.app.state.settings).logout(session, request.cookies.get(COOKIE_NAME))
    response = Response(status_code=204)
    response.delete_cookie(
        COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/me", response_model=UserProfileDto, operation_id="get_current_user")
def me(user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return UserProfileDto.model_validate(user)
