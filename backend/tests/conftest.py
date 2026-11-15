import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app
from app.migrations import upgrade
from app.seed import seed_demo

DEMO_PASSWORD = "test-demo-password-only-2026"


@pytest.fixture
def settings():
    url = os.getenv("TEST_DATABASE_URL")
    if not url or not (make_url(url).database or "").endswith("_test"):
        raise pytest.UsageError("Set TEST_DATABASE_URL to a PostgreSQL database ending in _test")
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=url,
        database_schema="test_" + uuid4().hex[:20],
        jwt_secret_key=uuid4().hex + uuid4().hex,
        cookie_secure=False,
        seed_demo=True,
        demo_password=DEMO_PASSWORD,
        allowed_origins=["http://testserver"],
    )


@pytest.fixture
def database(settings):
    # Only a newly generated schema inside the explicitly named test database is removed.
    administration = Database(settings.model_copy(update={"database_schema": "public"}))
    with administration.engine.begin() as connection:
        connection.execute(CreateSchema(settings.database_schema))
    database = Database(settings)
    try:
        upgrade(settings)
        seed_demo(settings, database)
        yield database
    finally:
        database.close()
        with administration.engine.begin() as connection:
            connection.execute(DropSchema(settings.database_schema, cascade=True))
        administration.close()


@pytest.fixture
def application(settings, database):
    return create_app(settings)


@pytest.fixture
def client(application):
    with TestClient(application) as connection:
        yield connection


@pytest.fixture
def login(client):
    def authenticate(email="manager@example.com"):
        response = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
        assert response.status_code == 200
        return response

    return authenticate
