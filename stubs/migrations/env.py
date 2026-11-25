from stubs.store import Base, database

from alembic import context

settings = context.config.attributes["settings"]


def include_object(_object, name, type_, _reflected, _compare_to):
    return not (type_ == "table" and name == "alembic_version")


engine, _sessions = database(settings)
try:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            version_table_schema=settings.stub_schema,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
