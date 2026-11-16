from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_engine(
            settings.database_url.get_secret_value(),
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={
                "connect_timeout": 5,
                "options": f"-csearch_path={settings.database_schema},public -ctimezone=UTC",
            },
        )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def close(self):
        self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.database.sessions() as session:
        yield session


DbSession = Annotated[Session, Depends(get_session)]
