import uvicorn

from app.core.config import get_settings
from app.core.database import Database
from app.migrations import upgrade
from app.seed import seed_demo


def main():
    settings = get_settings()
    upgrade(settings)
    database = Database(settings)
    try:
        seed_demo(settings, database)
    finally:
        database.close()
    uvicorn.run(
        "app.main:create_app", factory=True, host=settings.backend_host, port=settings.backend_port
    )


if __name__ == "__main__":
    main()
