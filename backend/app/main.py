import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.database import Database, DbSession
from app.core.errors import register_errors
from app.core.public_privacy import PublicResponsePrivacy
from app.modules.auth.directory import router as users_router
from app.modules.auth.models import User
from app.modules.auth.router import router as auth_router
from app.modules.bookings.financial import router as financial_router
from app.modules.bookings.router import router as bookings_router
from app.modules.clients.router import router as clients_router
from app.modules.communications.router import router as communications_router
from app.modules.notifications.router import router as notifications_router
from app.modules.payments.adapter import StubAdapter
from app.modules.payments.events import router as payment_events_router
from app.modules.payments.reconciliation import Reconciler
from app.modules.payments.router import router as payments_router
from app.modules.requests.router import router as requests_router
from app.modules.tourists.router import public_router as public_tourists_router
from app.modules.tourists.router import router as tourists_router
from app.modules.tours.router import router as tours_router
from app.modules.tours.selection_router import public_router as public_selections_router
from app.modules.tours.selection_router import router as selections_router


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or get_settings()
    database = Database(configuration)

    @asynccontextmanager
    async def lifespan(_app):
        worker = (
            Reconciler(database, _app.state.payment_adapter)
            if configuration.payment_reconciliation_enabled
            and _app.state.payment_adapter.configured()
            else None
        )
        task = asyncio.create_task(worker.run()) if worker else None
        try:
            yield
        finally:
            try:
                if worker:
                    worker.stop.set()
                    await task
            finally:
                database.close()

    application = FastAPI(title="TravelCRM backend", version="0.1.0", lifespan=lifespan)
    application.state.settings = configuration
    application.state.database = database
    application.state.payment_adapter = StubAdapter(configuration)
    register_errors(application)
    application.add_middleware(PublicResponsePrivacy)
    application.include_router(auth_router)
    application.include_router(clients_router)
    application.include_router(users_router)
    application.include_router(requests_router)
    application.include_router(tours_router)
    application.include_router(communications_router)
    application.include_router(selections_router)
    application.include_router(public_selections_router)
    application.include_router(tourists_router)
    application.include_router(public_tourists_router)
    application.include_router(bookings_router)
    application.include_router(payments_router)
    application.include_router(payment_events_router)
    application.include_router(notifications_router)
    application.include_router(financial_router)

    @application.get("/api/health/live", tags=["health"])
    def live():
        return {"status": "ok"}

    @application.get("/api/health/ready", tags=["health"])
    def ready(session: DbSession):
        session.execute(select(User.id).limit(1)).all()
        return {"status": "ok"}

    return application
