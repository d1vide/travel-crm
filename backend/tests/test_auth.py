from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.main import create_app
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import RefreshToken, Role, User
from app.modules.auth.security import access_token, hash_refresh, utcnow
from tests.conftest import DEMO_PASSWORD


@pytest.mark.parametrize(
    "email,role",
    [
        ("manager@example.com", "manager"),
        ("head@example.com", "head"),
        ("accountant@example.com", "accountant"),
    ],
)
def test_login_profile_cookie_and_hash(login, client, database, email, role):
    response = login(email)
    body = response.json()
    assert set(body) == {"access_token", "user"}
    assert set(body["user"]) == {"id", "full_name", "role"}
    assert body["user"]["role"] == role
    assert response.headers["cache-control"] == "no-store"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/auth" in cookie
    raw = client.cookies.get("refresh_token")
    with database.sessions() as session:
        token = session.scalar(select(RefreshToken))
        assert token.token_hash == hash_refresh(raw) and raw != token.token_hash
    me = client.get("/api/auth/me", headers={"Authorization": "Bearer " + body["access_token"]})
    assert me.status_code == 200
    assert {key: me.json()[key] for key in body["user"]} == body["user"]
    assert me.json()["email"] == email


@pytest.mark.parametrize(
    "email,password", [("missing@example.com", DEMO_PASSWORD), ("manager@example.com", "wrong")]
)
def test_invalid_login_has_no_session(client, database, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401 and response.json()["code"] == "unauthorized"
    assert response.json()["fields"] == []
    assert "set-cookie" not in response.headers
    with database.sessions() as session:
        assert session.scalar(select(RefreshToken)) is None


def test_refresh_rotates_and_replay_revokes_family(login, client, database):
    login()
    original = client.cookies.get("refresh_token")
    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    replacement = client.cookies.get("refresh_token")
    assert replacement != original
    replay = client.post("/api/auth/refresh", headers={"Cookie": "refresh_token=" + original})
    assert replay.status_code == 401
    assert (
        client.post(
            "/api/auth/refresh", headers={"Cookie": "refresh_token=" + replacement}
        ).status_code
        == 401
    )
    with database.sessions() as session:
        tokens = session.scalars(select(RefreshToken)).all()
        assert len(tokens) == 2 and all(token.revoked_at is not None for token in tokens)


def test_logout_revokes_cookie_and_is_repeatable(login, client):
    response = login()
    refresh = client.cookies.get("refresh_token")
    access = response.json()["access_token"]
    assert client.post("/api/auth/logout").status_code == 204
    assert client.cookies.get("refresh_token") is None
    assert client.post("/api/auth/logout").status_code == 204
    assert (
        client.post("/api/auth/refresh", headers={"Cookie": "refresh_token=" + refresh}).status_code
        == 401
    )
    # Short-lived access remains valid, as specified; logout immediately revokes refresh.
    assert (
        client.get("/api/auth/me", headers={"Authorization": "Bearer " + access}).status_code == 200
    )


@pytest.mark.parametrize("cookie", [None, "unknown"])
def test_refresh_without_valid_cookie(client, cookie):
    headers = {"Cookie": "refresh_token=" + cookie} if cookie else {}
    assert client.post("/api/auth/refresh", headers=headers).status_code == 401


def test_expired_refresh_is_revoked(login, client, database):
    login()
    with database.sessions.begin() as session:
        session.execute(
            update(RefreshToken).values(
                created_at=utcnow() - timedelta(days=2), expires_at=utcnow() - timedelta(days=1)
            )
        )
    assert client.post("/api/auth/refresh").status_code == 401
    with database.sessions() as session:
        assert session.scalar(select(RefreshToken.revoked_at)) is not None


def test_inactive_user_cannot_login_or_use_tokens(login, client, database):
    result = login()
    with database.sessions.begin() as session:
        session.execute(
            update(User).where(User.email == "manager@example.com").values(is_active=False)
        )
    assert (
        client.post(
            "/api/auth/login", json={"email": "manager@example.com", "password": DEMO_PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": "Bearer " + result.json()["access_token"]}
        ).status_code
        == 401
    )
    assert client.post("/api/auth/refresh").status_code == 401


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "malformed",
        "expired",
        "wrong_issuer",
        "missing_claims",
        "invalid_subject",
        "wrong_audience",
        "wrong_signature",
        "unsigned",
        "unknown_user",
    ],
)
def test_invalid_access_token(client, database, settings, kind):
    with database.sessions() as session:
        user_id = session.scalar(select(User.id))
    if kind == "missing":
        headers = {}
    else:
        token = "not-a-jwt"
        if kind == "expired":
            token = access_token(user_id, settings, now=utcnow() - timedelta(hours=1))
        elif kind in (
            "wrong_issuer",
            "missing_claims",
            "invalid_subject",
            "wrong_audience",
            "wrong_signature",
            "unsigned",
            "unknown_user",
        ):
            payload = jwt.decode(
                access_token(user_id, settings), options={"verify_signature": False}
            )
            if kind == "wrong_issuer":
                payload["iss"] = "another-service"
            elif kind == "missing_claims":
                payload.pop("exp")
            elif kind == "invalid_subject":
                payload["sub"] = "not-a-uuid"
            elif kind == "wrong_audience":
                payload["aud"] = "another-client"
            elif kind == "unknown_user":
                payload["sub"] = str(uuid4())
            key = "" if kind == "unsigned" else settings.jwt_secret_key.get_secret_value()
            if kind == "wrong_signature":
                key = uuid4().hex + uuid4().hex
            token = jwt.encode(payload, key, algorithm="none" if kind == "unsigned" else "HS256")
        headers = {"Authorization": "Bearer " + token}
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 401 and response.json()["code"] == "unauthorized"


def test_role_dependency_enforces_head_only(application, client, login):
    @application.get("/test/head-only", dependencies=[Depends(require_roles(Role.HEAD))])
    def head_only():
        return {"ok": True}

    for email, status in [
        ("manager@example.com", 403),
        ("head@example.com", 200),
        ("accountant@example.com", 403),
    ]:
        token = login(email).json()["access_token"]
        assert (
            client.get("/test/head-only", headers={"Authorization": "Bearer " + token}).status_code
            == status
        )


def test_parallel_refresh_serializes_and_revokes_replayed_family(login, client, settings, database):
    login()
    raw = client.cookies.get("refresh_token")
    barrier = Barrier(2)

    def refresh_once():
        with TestClient(create_app(settings)) as connection:
            barrier.wait(timeout=10)
            response = connection.post(
                "/api/auth/refresh", headers={"Cookie": "refresh_token=" + raw}
            )
            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _item: refresh_once(), range(2)))
    assert sorted(results) == [200, 401]
    with database.sessions() as session:
        assert all(token.revoked_at is not None for token in session.scalars(select(RefreshToken)))


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/refresh", "/api/auth/logout"])
def test_cross_origin_rejected_before_session_changes(client, path):
    response = client.post(
        path,
        headers={"Origin": "https://untrusted.example", "Sec-Fetch-Site": "cross-site"},
        json={"email": "manager@example.com", "password": DEMO_PASSWORD},
    )
    assert response.status_code == 403 and response.json()["code"] == "forbidden"


def test_allowed_origin_and_case_normalization(client):
    response = client.post(
        "/api/auth/login",
        headers={"Origin": "http://testserver"},
        json={"email": "MANAGER@EXAMPLE.COM", "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200


def test_secure_cookie_for_https(settings, database):
    production = settings.model_copy(
        update={"app_env": "production", "seed_demo": False, "cookie_secure": True}
    )
    with TestClient(create_app(production), base_url="https://testserver") as connection:
        response = connection.post(
            "/api/auth/login", json={"email": "manager@example.com", "password": DEMO_PASSWORD}
        )
        assert response.status_code == 200 and "Secure" in response.headers["set-cookie"]
