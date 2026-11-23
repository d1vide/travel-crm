from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.database import Database, DbSession
from app.core.errors import register_errors
from app.modules.auth.directory import router as users_router
from app.modules.auth.models import User
from app.modules.auth.router import router as auth_router
from app.modules.clients.router import router as clients_router
from app.modules.requests.router import router as requests_router


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or get_settings()
    database = Database(configuration)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            database.close()

    application = FastAPI(title="TravelCRM backend", version="0.1.0", lifespan=lifespan)
    application.state.settings = configuration
    application.state.database = database
    register_errors(application)
    application.include_router(auth_router)
    application.include_router(clients_router)
    application.include_router(users_router)
    application.include_router(requests_router)

    @application.get("/api/health/live", tags=["health"])
    def live():
        return {"status": "ok"}

    @application.get("/api/health/ready", tags=["health"])
    def ready(session: DbSession):
        session.execute(select(User.id).limit(1)).all()
        return {"status": "ok"}

    return application
