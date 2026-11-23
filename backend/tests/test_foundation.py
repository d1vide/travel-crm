import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import Settings
from app.core.database import Database
from app.core.errors import ErrorCode
from app.main import create_app
from app.migrations import migration_config, upgrade
from app.modules.auth.models import Role, User
from app.modules.auth.security import password_hasher
from app.seed import seed_demo

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = json.loads((ROOT / "docs/api/domain.schema.json").read_text(encoding="utf-8"))


def validate(name, value):
    Draft202012Validator(
        {"$ref": f"#/$defs/{name}", "$defs": DOMAIN["$defs"]}, format_checker=FormatChecker()
    ).validate(value)


def test_migrations_reapply_and_seed_preserves_existing_users(settings, database):
    inspector = inspect(database.engine)
    assert inspector.has_table("users", schema=settings.database_schema)
    assert inspector.has_table("alembic_version", schema=settings.database_schema)
    with database.sessions() as session:
        before = {
            user.email: (user.id, user.password_hash) for user in session.scalars(select(User))
        }
    upgrade(settings)
    seed_demo(settings, database)
    with database.sessions() as session:
        after = {
            user.email: (user.id, user.password_hash) for user in session.scalars(select(User))
        }
    assert before == after and len(after) == 3
    command.check(migration_config(settings))


def test_migration_roundtrip_in_isolated_test_schema(settings, database):
    command.downgrade(migration_config(settings), "base")
    upgrade(settings)
    seed_demo(settings, database)
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 3


def test_password_hashes_and_restart_persistence(settings, database):
    with database.sessions() as session:
        users = session.scalars(select(User)).all()
        ids = {user.id for user in users}
        for user in users:
            assert user.password_hash.startswith("$argon2id$")
            assert password_hasher.verify(
                settings.demo_password.get_secret_value(), user.password_hash
            )
    reconnected = Database(settings)
    try:
        with reconnected.sessions() as session:
            assert {user.id for user in session.scalars(select(User))} == ids
    finally:
        reconnected.close()


@pytest.mark.parametrize(
    "column,value",
    [
        ("email", "UPPER@EXAMPLE.COM"),
        ("email", "manager@example.com"),
        ("role", "admin"),
        ("full_name", " "),
    ],
)
def test_database_constraints(database, column, value):
    values = {
        "email": "new@example.com",
        "full_name": "Тест",
        "role": Role.MANAGER,
        "password_hash": "test-only",
    }
    values[column] = value
    with database.sessions() as session:
        session.add(User(**values))
        with pytest.raises(IntegrityError):
            session.commit()


def test_auth_and_errors_follow_frozen_contract(login, client):
    result = login()
    validate("AuthResult", result.json())
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer " + result.json()["access_token"]}
    )
    validate("User", response.json())
    for payload in [
        {"email": "invalid", "password": "private-fixture"},
        {"email": "manager@example.com", "password": 123},
        {"email": "manager@example.com", "password": "private-fixture", "role": "head"},
    ]:
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 422
        validate("Error", response.json())
        assert "private-fixture" not in response.text
    assert {role.value for role in Role} == set(DOMAIN["$defs"]["Role"]["enum"])
    assert {code.value for code in ErrorCode} == set(DOMAIN["$defs"]["ErrorCode"]["enum"])


def test_runtime_auth_operation_ids_match_contract(application):
    baseline = json.loads((ROOT / "docs/api/openapi.json").read_text(encoding="utf-8"))
    runtime = application.openapi()
    implemented = {
        operation["operationId"]
        for path in baseline["paths"].values()
        for operation in path.values()
        if operation.get("x-implementation-status") == "implemented"
    }
    runtime_operations = {
        operation["operationId"]
        for path, methods in runtime["paths"].items()
        if path in baseline["paths"]
        for operation in methods.values()
    }
    assert implemented == runtime_operations
    for path in ("/api/auth/login", "/api/auth/refresh", "/api/auth/logout", "/api/auth/me"):
        method = "get" if path.endswith("/me") else "post"
        assert (
            runtime["paths"][path][method]["operationId"]
            == baseline["paths"][path][method]["operationId"]
        )
    assert runtime["paths"]["/api/auth/me"]["get"]["security"] == [{"BearerAuth": []}]
    assert runtime["paths"]["/api/auth/refresh"]["post"]["security"] == [{"RefreshCookie": []}]


def test_health_and_database_outage(client, settings):
    assert client.get("/api/health/live").status_code == 200
    assert client.get("/api/health/ready").status_code == 200
    unavailable = settings.model_copy(
        update={
            "database_url": SecretStr("postgresql+psycopg://nobody:private@127.0.0.1:1/unavailable")
        }
    )
    with TestClient(create_app(unavailable)) as connection:
        assert connection.get("/api/health/live").status_code == 200
        response = connection.get("/api/health/ready")
        assert response.status_code == 503
        validate("Error", response.json())
        assert "private" not in response.text and "127.0.0.1" not in response.text


@pytest.mark.parametrize(
    "changes",
    [
        {"jwt_secret_key": "short"},
        {"database_url": "sqlite:///local.db"},
        {"database_schema": "public;drop"},
        {"app_env": "production", "cookie_secure": False},
        {"seed_demo": True},
    ],
)
def test_invalid_configuration_fails(changes):
    values = {
        "database_url": "postgresql+psycopg://local:local@localhost/travelcrm",
        "jwt_secret_key": uuid4().hex + uuid4().hex,
        "seed_demo": False,
    }
    values.update(changes)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_environment_initializer_is_safe_and_repeatable(tmp_path, monkeypatch, capsys):
    source = ROOT / "scripts/init_env.py"
    spec = importlib.util.spec_from_file_location("init_env", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "scripts/init_env.py"))
    module.main()
    result = (tmp_path / ".env").read_bytes()
    values = dict(line.split("=", 1) for line in result.decode().splitlines())
    assert len(values["JWT_SECRET_KEY"]) >= 32
    assert values["JWT_SECRET_KEY"] not in capsys.readouterr().out
    module.main()
    assert (tmp_path / ".env").read_bytes() == result
