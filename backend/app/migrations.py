from alembic.config import Config

from alembic import command
from app.core.config import BACKEND_ROOT, Settings


def migration_config(settings: Settings) -> Config:
    configuration = Config(str(BACKEND_ROOT / "alembic.ini"))
    configuration.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    configuration.attributes["settings"] = settings
    return configuration


def upgrade(settings: Settings):
    command.upgrade(migration_config(settings), "head")
