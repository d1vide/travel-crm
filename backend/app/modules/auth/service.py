from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.schemas import AuthResult, UserDto
from app.modules.auth.security import (
    DUMMY_PASSWORD_HASH,
    access_token,
    hash_refresh,
    new_refresh,
    password_hasher,
    utcnow,
)


@dataclass(frozen=True)
class SessionResult:
    body: AuthResult
    refresh: str = field(repr=False)


def unauthorized():
    return ApiError(401, "unauthorized", "Неверные данные входа или сессия недействительна")


class AuthService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _new_token(self, user_id: UUID, family_id: UUID):
        raw = new_refresh()
        row = RefreshToken(
            id=uuid4(),
            user_id=user_id,
            family_id=family_id,
            token_hash=hash_refresh(raw),
            expires_at=utcnow() + timedelta(days=self.settings.refresh_token_days),
        )
        return raw, row

    def _result(self, user: User, raw: str):
        return SessionResult(
            AuthResult(
                access_token=access_token(user.id, self.settings), user=UserDto.model_validate(user)
            ),
            raw,
        )

    def login(self, session: Session, email: str, password: str) -> SessionResult:
        user = session.scalar(select(User).where(User.email == email.lower()))
        valid = password_hasher.verify(
            password, user.password_hash if user else DUMMY_PASSWORD_HASH
        )
        if not valid or user is None or not user.is_active:
            raise unauthorized()
        raw, token = self._new_token(user.id, uuid4())
        session.add(token)
        session.commit()
        return self._result(user, raw)

    def _locked_token(self, session: Session, raw: str) -> tuple[RefreshToken, User] | None:
        token_hash = hash_refresh(raw)
        initial = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        if initial is None:
            return None
        # One lock order for rotation, replay revocation and logout avoids family deadlocks.
        user = session.scalar(select(User).where(User.id == initial.user_id).with_for_update())
        token = session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return token, user

    def _revoke_family(self, session: Session, family_id: UUID):
        session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )

    def refresh(self, session: Session, raw: str | None) -> SessionResult:
        locked = self._locked_token(session, raw) if raw else None
        if locked is None:
            raise unauthorized()
        token, user = locked
        if token.revoked_at is not None or token.expires_at <= utcnow() or not user.is_active:
            self._revoke_family(session, token.family_id)
            session.commit()  # Revocation survives the HTTP 401.
            raise unauthorized()
        new_raw, replacement = self._new_token(user.id, token.family_id)
        session.add(replacement)
        session.flush()
        token.revoked_at = utcnow()
        token.replaced_by_id = replacement.id
        session.commit()
        return self._result(user, new_raw)

    def logout(self, session: Session, raw: str | None):
        locked = self._locked_token(session, raw) if raw else None
        if locked is not None:
            self._revoke_family(session, locked[0].family_id)
            session.commit()
