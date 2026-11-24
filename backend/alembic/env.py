from alembic import context
from app.core import (
    audit,  # noqa: F401
    idempotency,  # noqa: F401
    public_links,  # noqa: F401
)
from app.core.config import get_settings
from app.core.database import Base, Database
from app.modules.auth import models  # noqa: F401
from app.modules.clients import models as client_models  # noqa: F401
from app.modules.communications import models as communication_models  # noqa: F401
from app.modules.requests import models as request_models  # noqa: F401
from app.modules.tours import models as tour_models  # noqa: F401
from app.modules.tours import selection_models  # noqa: F401

configuration = context.config
settings = configuration.attributes.get("settings") or get_settings()


def include_object(_object, name, type_, _reflected, _compare_to):
    # The version table may also be visible through public in search_path.
    return not (type_ == "table" and name == "alembic_version")


def configure(connection=None, url=None):
    context.configure(
        connection=connection,
        url=url,
        target_metadata=Base.metadata,
        version_table_schema=settings.database_schema,
        include_object=include_object,
        compare_type=True,
        literal_binds=connection is None,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    configure(url=settings.database_url.get_secret_value())
else:
    database = Database(settings)
    try:
        with database.engine.connect() as connection:
            configure(connection=connection)
    finally:
        database.close()
