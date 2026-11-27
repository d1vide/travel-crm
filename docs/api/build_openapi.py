"""Export the application contract without connecting to PostgreSQL or loading .env."""

import argparse
import json
import sys
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(DIRECTORY.parents[1] / "backend"))


def build():
    from app.core.config import Settings
    from app.main import create_app

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://export:export@127.0.0.1/export_test",
        jwt_secret_key="openapi-export-placeholder-key-000000000",
        seed_demo=False,
        payment_stub_key=None,
        payment_reconciliation_enabled=False,
    )
    application = create_app(settings)
    try:
        return application.openapi()
    finally:
        application.state.database.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    document = build()
    target = DIRECTORY / "openapi.json"
    if args.check:
        if not target.exists() or json.loads(target.read_text(encoding="utf-8")) != document:
            raise SystemExit("OpenAPI is stale; run build_openapi.py")
        print("OpenAPI matches registered routes and Pydantic models.")
    else:
        target.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("Written openapi.json")


if __name__ == "__main__":
    main()
