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
DEMO_PROFILES = {
    Role.MANAGER: ("Учебный отдел продаж", "Менеджер по туризму", "+7 000 000-00-01"),
    Role.HEAD: ("Учебный отдел продаж", "Руководитель отдела продаж", "+7 000 000-00-02"),
    Role.ACCOUNTANT: ("Учебная бухгалтерия", "Бухгалтер", "+7 000 000-00-03"),
}


def seed_demo(settings: Settings, database: Database):
    if not settings.seed_demo:
        return
    with database.sessions.begin() as session:
        session.execute(select(func.pg_advisory_xact_lock(914202609)))
        for email, full_name, role in DEMO_USERS:
            if session.scalar(select(User.id).where(User.email == email)) is None:
                department, position, work_phone = DEMO_PROFILES[role]
                session.add(
                    User(
                        email=email,
                        full_name=full_name,
                        role=role,
                        department=department,
                        position=position,
                        work_phone=work_phone,
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
