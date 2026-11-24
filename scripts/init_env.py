"""Create local development configuration without overwriting an existing file."""

import secrets
from pathlib import Path


def main():
    destination = Path(__file__).resolve().parents[1] / ".env"
    if destination.exists():
        print(".env already exists; left unchanged.")
        return
    password = secrets.token_urlsafe(24)
    settings = {
        "APP_ENV": "development",
        "POSTGRES_PASSWORD": password,
        "POSTGRES_PORT": "5432",
        "DATABASE_URL": f"postgresql+psycopg://travelcrm:{password}@127.0.0.1:5432/travelcrm",
        "JWT_SECRET_KEY": secrets.token_urlsafe(48),
        "COOKIE_SECURE": "false",
        "SEED_DEMO": "true",
        "DEMO_PASSWORD": secrets.token_urlsafe(18),
        "BACKEND_PORT": "8000",
        "PUBLIC_APP_URL": "http://localhost:8080",
    }
    # Exclusive creation prevents accidental replacement by concurrent setup commands.
    with destination.open("x", encoding="utf-8", newline="\n") as output:
        output.write(
            "\n".join(f"{key}={value}" for key, value in settings.items()) + "\n"
        )
    print("Created .env with generated local secrets; keep it outside Git.")


if __name__ == "__main__":
    main()
