"""Create local development configuration without overwriting an existing file."""

import argparse
import secrets
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--add-payment-settings", action="store_true")
    args = parser.parse_args(argv or [])
    destination = Path(__file__).resolve().parents[1] / ".env"
    if destination.exists():
        if args.add_payment_settings:
            text = destination.read_text(encoding="utf-8")
            keys = {
                line.split("=", 1)[0].strip()
                for line in text.splitlines()
                if "=" in line and not line.lstrip().startswith("#")
            }
            additions = {
                "PAYMENT_STUB_URL": "http://127.0.0.1:8010",
                "PAYMENT_STUB_KEY": secrets.token_urlsafe(48),
                "PAYMENT_TIMEOUT_SECONDS": "1",
            }
            missing = {key: value for key, value in additions.items() if key not in keys}
            if missing:
                with destination.open("a", encoding="utf-8", newline="\n") as output:
                    output.write(
                        ("" if text.endswith("\n") else "\n")
                        + "\n".join(f"{key}={value}" for key, value in missing.items())
                        + "\n"
                    )
            print("Added missing payment settings; existing values preserved.")
            return
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
        "PAYMENT_STUB_URL": "http://127.0.0.1:8010",
        "PAYMENT_STUB_KEY": secrets.token_urlsafe(48),
        "PAYMENT_TIMEOUT_SECONDS": "1",
    }
    # Exclusive creation prevents accidental replacement by concurrent setup commands.
    with destination.open("x", encoding="utf-8", newline="\n") as output:
        output.write("\n".join(f"{key}={value}" for key, value in settings.items()) + "\n")
    print("Created .env with generated local secrets; keep it outside Git.")


if __name__ == "__main__":
    main(sys.argv[1:])
