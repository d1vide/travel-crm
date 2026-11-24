import base64
import hashlib
import re
import secrets
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PublicLink(Base):
    __tablename__ = "public_links"
    __table_args__ = (
        CheckConstraint(
            "(purpose = 'selection' AND selection_id IS NOT NULL AND request_id IS NULL) OR (purpose = 'tourists' AND request_id IS NOT NULL AND selection_id IS NULL)",
            name="purpose_target",
        ),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="valid_token_hash"),
        CheckConstraint("expires_at > created_at", name="positive_lifetime"),
        Index(
            "uq_public_links_live_selection",
            "selection_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL AND purpose = 'selection'"),
        ),
        Index(
            "uq_public_links_live_request",
            "request_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL AND purpose = 'tourists'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    purpose: Mapped[str] = mapped_column(String(16))
    request_id: Mapped[UUID | None] = mapped_column(ForeignKey("requests.id", ondelete="RESTRICT"))
    selection_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("selections.id", ondelete="RESTRICT")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def token_hash(token: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    decoded = base64.urlsafe_b64decode(token + "=")
    if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode().rstrip("=") != token:
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_token():
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)
