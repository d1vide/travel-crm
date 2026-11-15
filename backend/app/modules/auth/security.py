import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings
from app.core.errors import ApiError

password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash("timing-only-not-a-login-password")


def utcnow() -> datetime:
    return datetime.now(UTC)


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_refresh() -> str:
    return secrets.token_urlsafe(32)


def access_token(user_id: UUID, settings: Settings, *, now: datetime | None = None) -> str:
    issued_at = now or utcnow()
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": issued_at,
            "exp": issued_at + timedelta(minutes=settings.access_token_minutes),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "jti": str(uuid4()),
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )


def token_subject(token: str, settings: Settings) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "iat", "exp", "iss", "aud", "jti"]},
        )
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError) as error:
        raise ApiError(401, "unauthorized", "Сессия недействительна или истекла") from error
