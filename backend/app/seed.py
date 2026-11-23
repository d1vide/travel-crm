from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.core.database import Database
from app.modules.auth.models import Role, User
from app.modules.auth.security import password_hasher
from app.modules.tours.seed import seed_tours

DEMO_USERS = (
    ("manager@example.com", "Тестовый менеджер", Role.MANAGER),
    ("head@example.com", "Тестовый руководитель", Role.HEAD),
    ("accountant@example.com", "Тестовый бухгалтер", Role.ACCOUNTANT),
)


def seed_demo(settings: Settings, database: Database):
    if not settings.seed_demo:
        return
    with database.sessions.begin() as session:
        session.execute(select(func.pg_advisory_xact_lock(914202609)))
        for email, full_name, role in DEMO_USERS:
            if session.scalar(select(User.id).where(User.email == email)) is None:
                session.add(
                    User(
                        email=email,
                        full_name=full_name,
                        role=role,
                        password_hash=password_hasher.hash(
                            settings.demo_password.get_secret_value()
                        ),
                    )
                )
        seed_tours(session)


def main():
    settings = get_settings()
    database = Database(settings)
    try:
        seed_demo(settings, database)
    finally:
        database.close()


if __name__ == "__main__":
    main()
