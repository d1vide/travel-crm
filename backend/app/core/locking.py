import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def lock_key(session: Session, value: str):
    number = int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big", signed=True)
    session.execute(select(func.pg_advisory_xact_lock(number)))


def lock_contacts(session: Session, contacts: set[tuple[str, str]]):
    for kind, value in sorted(contacts):
        lock_key(session, f"client-contact:{kind}:{value}")
