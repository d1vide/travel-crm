from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.schema import CreateSchema

from stubs.store import database


def upgrade(settings):
    engine, _sessions = database(settings)
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(settings.stub_schema, if_not_exists=True))
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        config.attributes["settings"] = settings
        command.upgrade(config, "head")
    finally:
        engine.dispose()
