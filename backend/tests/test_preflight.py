import httpx
import pytest
from sqlalchemy import func, select, update

from app import preflight
from app.modules.auth.models import RefreshToken, User
from app.modules.tours.models import TourOffer
from app.preflight import inspect_demo


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"payment_stub_key": settings.jwt_secret_key})


def http_client(*, api_status=200, payment_status=404):
    def respond(request):
        if request.url.path == "/":
            return httpx.Response(
                200, text='<div id="app"></div>', headers={"content-type": "text/html"}
            )
        if request.url.path.startswith("/v1/payments/"):
            assert request.headers["authorization"].startswith("Bearer ")
            return httpx.Response(payment_status, json={"detail": "Operation not found"})
        return httpx.Response(api_status, json={"status": "ok"})

    return httpx.Client(transport=httpx.MockTransport(respond))


def test_demo_preflight_passes_without_mutating_database(settings, database):
    with database.sessions() as session:
        users = [(user.id, user.password_hash) for user in session.scalars(select(User))]
        tours = session.scalar(select(func.count()).select_from(TourOffer))
    with http_client() as http:
        results = inspect_demo(settings, database, http)
    assert len(results) == 7 and all(item.ok for item in results)
    with database.sessions() as session:
        assert [(user.id, user.password_hash) for user in session.scalars(select(User))] == users
        assert session.scalar(select(func.count()).select_from(TourOffer)) == tours
        assert session.scalar(select(func.count()).select_from(RefreshToken)) == 0


@pytest.mark.parametrize("change", ["password", "role", "inactive", "catalogue", "migration"])
def test_demo_preflight_detects_incomplete_environment(settings, database, change):
    with database.sessions.begin() as session:
        if change == "password":
            settings = settings.model_copy(update={"demo_password": settings.jwt_secret_key})
        elif change == "role":
            session.execute(
                update(User).where(User.email == "manager@example.com").values(role="head")
            )
        elif change == "inactive":
            session.execute(
                update(User).where(User.email == "manager@example.com").values(is_active=False)
            )
        elif change == "catalogue":
            session.execute(update(TourOffer).values(is_active=False))
        else:
            from sqlalchemy import text

            session.execute(text("UPDATE alembic_version SET version_num = '0011_refunds'"))
    with http_client() as http:
        results = inspect_demo(settings, database, http)
    expected = (
        "Каталог"
        if change == "catalogue"
        else "Миграции БД"
        if change == "migration"
        else "Демо-сотрудники"
    )
    assert not next(item for item in results if item.name == expected).ok


def test_demo_preflight_rejects_failed_api_and_wrong_provider_key(settings, database):
    with http_client(api_status=503, payment_status=401) as http:
        results = inspect_demo(settings, database, http)
    failed = {item.name for item in results if not item.ok}
    assert failed == {"API через web", "Платёжная заглушка", "Доступ backend к заглушке"}


def test_demo_preflight_does_not_disclose_network_exception(settings, database):
    def fail(request):
        raise httpx.ConnectError("PRIVATE-PASSWORD-TOKEN-URL", request=request)

    with httpx.Client(transport=httpx.MockTransport(fail)) as http:
        results = inspect_demo(settings, database, http)
    assert sum(not item.ok for item in results) == 4
    assert "PRIVATE" not in repr(results)


def test_demo_preflight_uses_web_override_without_changing_settings(settings, database):
    seen = []

    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(503)

    original = settings.public_app_url
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        inspect_demo(settings, database, http, web_url="http://web:8080")
    assert "http://web:8080/" in seen and "http://web:8080/api/health/ready" in seen
    assert settings.public_app_url == original


def test_demo_preflight_config_failure_exits_without_secrets(monkeypatch, capsys):
    def invalid():
        raise ValueError("PRIVATE-CONNECTION-PASSWORD")

    monkeypatch.setattr("sys.argv", ["preflight"])
    monkeypatch.setattr(preflight, "get_settings", invalid)
    assert preflight.main() == 1
    output = capsys.readouterr()
    assert "[FAIL]" in output.out and "PRIVATE" not in output.out + output.err
