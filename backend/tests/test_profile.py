import pytest
from sqlalchemy import select, update

from alembic import command
from app.migrations import migration_config, upgrade
from app.modules.auth.models import User
from app.seed import DEMO_PROFILES, seed_demo
from tests.test_foundation import validate


def profile(client, login, email="manager@example.com"):
    token = login(email).json()["access_token"]
    return client.get("/api/auth/me", headers={"Authorization": "Bearer " + token})


@pytest.mark.parametrize(
    "email", ["manager@example.com", "head@example.com", "accountant@example.com"]
)
def test_profile_returns_own_demo_fields_for_every_role(client, login, email):
    response = profile(client, login, email)
    assert response.status_code == 200
    validate("UserProfile", response.json())
    body = response.json()
    assert body["email"] == email
    assert (body["department"], body["position"], body["work_phone"]) == DEMO_PROFILES[body["role"]]
    assert response.headers["Cache-Control"] == "no-store"


def test_profile_nulls_and_seed_preserve_existing_account(client, login, database, settings):
    with database.sessions.begin() as session:
        session.execute(
            update(User)
            .where(User.email == "manager@example.com")
            .values(department=None, position="Учебная должность", work_phone=None)
        )
        before = session.scalar(select(User).where(User.email == "manager@example.com"))
        identity, hashed = before.id, before.password_hash
    seed_demo(settings, database)
    seed_demo(settings, database)
    response = profile(client, login)
    validate("UserProfile", response.json())
    assert response.json()["department"] is None
    assert response.json()["position"] == "Учебная должность"
    assert response.json()["work_phone"] is None
    with database.sessions() as session:
        after = session.get(User, identity)
        assert after.password_hash == hashed and after.email == "manager@example.com"


def test_profile_fields_do_not_expand_login_refresh_or_assignee_directory(client, login):
    signed_in = login("head@example.com").json()
    refreshed = client.post("/api/auth/refresh").json()
    for result in (signed_in, refreshed):
        validate("AuthResult", result)
        assert set(result["user"]) == {"id", "full_name", "role"}
    response = client.get(
        "/api/users", headers={"Authorization": "Bearer " + refreshed["access_token"]}
    )
    assert response.status_code == 200 and response.json()["items"]
    for item in response.json()["items"]:
        assert set(item) == {"id", "full_name", "role"}


def test_profile_migration_preserves_existing_users(database, settings):
    with database.sessions() as session:
        before = {
            row.id: (row.email, row.full_name, row.role, row.password_hash, row.is_active)
            for row in session.scalars(select(User))
        }
    command.downgrade(migration_config(settings), "0011_refunds")
    upgrade(settings)
    seed_demo(settings, database)
    with database.sessions() as session:
        users = session.scalars(select(User)).all()
        assert {
            row.id: (row.email, row.full_name, row.role, row.password_hash, row.is_active)
            for row in users
        } == before
        assert all(row.department is row.position is row.work_phone is None for row in users)
    command.check(migration_config(settings))
