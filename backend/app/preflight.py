"""Read-only checks for a local demonstration environment."""

import argparse
from dataclasses import dataclass
from uuid import uuid4

import httpx
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import select, text

from app.core.config import Settings, get_settings
from app.core.database import Database
from app.migrations import migration_config
from app.modules.auth.models import User
from app.modules.auth.security import password_hasher
from app.modules.tours.models import TourOffer
from app.seed import DEMO_USERS


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    hint: str


def inspect_demo(settings, database, http, *, web_url=None):
    results = []
    web_origin = Settings.public_origin(web_url or settings.public_app_url)

    def check(name, probe, hint):
        try:
            ok = bool(probe())
        except Exception:
            # Exceptions may contain database credentials, URLs or provider responses.
            ok = False
        results.append(Check(name, ok, hint))

    def migrations():
        expected = set(ScriptDirectory.from_config(migration_config(settings)).get_heads())
        with database.engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            actual = set(
                MigrationContext.configure(
                    connection, opts={"version_table_schema": settings.database_schema}
                ).get_current_heads()
            )
        return actual == expected

    def employees():
        if not settings.seed_demo or settings.app_env == "production":
            return False
        with database.sessions() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            users = {
                user.email: user
                for user in session.scalars(
                    select(User).where(User.email.in_([item[0] for item in DEMO_USERS]))
                )
            }
            return all(
                email in users
                and users[email].is_active
                and users[email].role == role
                and password_hasher.verify(
                    settings.demo_password.get_secret_value(), users[email].password_hash
                )
                for email, _, role in DEMO_USERS
            )

    def catalogue():
        with database.sessions() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            return (
                session.scalar(select(TourOffer.id).where(TourOffer.is_active).limit(1)) is not None
            )

    def ready(url):
        response = http.get(url)
        return response.status_code == 200 and response.json() == {"status": "ok"}

    def web():
        response = http.get(web_origin + "/")
        return (
            response.status_code == 200
            and "text/html" in response.headers.get("content-type", "")
            and '<div id="app"' in response.text
        )

    def payment_access():
        if settings.payment_stub_key is None:
            return False
        response = http.get(
            settings.payment_stub_url + f"/v1/payments/{uuid4()}",
            headers={"Authorization": "Bearer " + settings.payment_stub_key.get_secret_value()},
        )
        return response.status_code == 404 and response.json() == {"detail": "Operation not found"}

    check("Миграции БД", migrations, "Выполните миграции до head; проверьте доступ к БД.")
    check(
        "Демо-сотрудники",
        employees,
        "Нужны SEED_DEMO=true и три активных демо-роли с текущим DEMO_PASSWORD. Seed не меняет существующие пароли.",
    )
    check("Каталог", catalogue, "Нужен хотя бы один активный тур; проверьте демо-seed.")
    check("Интерфейс", web, "Проверьте web/nginx и PUBLIC_APP_URL.")
    check(
        "API через web",
        lambda: ready(web_origin + "/api/health/ready"),
        "Проверьте backend, БД и прокси /api в nginx.",
    )
    check(
        "Платёжная заглушка",
        lambda: ready(settings.payment_stub_url + "/healthz"),
        "Проверьте stubs, его миграции и PAYMENT_STUB_URL.",
    )
    check(
        "Доступ backend к заглушке",
        payment_access,
        "Проверьте одинаковый PAYMENT_STUB_KEY у backend и stubs.",
    )
    return results


def main():
    parser = argparse.ArgumentParser(description="Проверка локального демонстрационного стенда")
    parser.add_argument(
        "--web-url", help="Адрес web из текущей среды, например http://web:8080 внутри Compose"
    )
    args = parser.parse_args()
    database = None
    try:
        settings = get_settings()
        database = Database(settings)
        with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as http:
            results = inspect_demo(settings, database, http, web_url=args.web_url)
    except Exception:
        print("[FAIL] Настройки стенда: проверьте .env по инструкции, секреты не выводятся.")
        return 1
    finally:
        if database is not None:
            database.close()
    for result in results:
        print(f"[{'OK' if result.ok else 'FAIL'}] {result.name}")
        if not result.ok:
            print("  " + result.hint)
    print("Проверка не заменяет оплату в браузере и полный приёмочный сценарий.")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
