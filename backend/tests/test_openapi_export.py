import importlib.util
import json
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends, Query
from jsonschema import Draft202012Validator
from pydantic import Field

from app import openapi
from app.core.config import Settings
from app.core.schemas import Dto
from app.main import create_app
from app.modules.auth.dependencies import require_roles
from app.modules.auth.models import Role

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def offline_app():
    application = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_url="postgresql+psycopg://export:export@127.0.0.1/export_test",
            jwt_secret_key="openapi-export-placeholder-key-000000000",
            seed_demo=False,
            payment_stub_key=None,
            payment_reconciliation_enabled=False,
        )
    )
    try:
        yield application
    finally:
        application.state.database.close()


def test_committed_contract_matches_runtime_without_database(offline_app, monkeypatch):
    def no_connection(*args, **kwargs):
        pytest.fail("Export must not connect to PostgreSQL")

    monkeypatch.setattr(offline_app.state.database.engine, "connect", no_connection)
    committed = json.loads((ROOT / "docs/api/openapi.json").read_text(encoding="utf-8"))
    assert offline_app.openapi() == committed
    assert offline_app.openapi() is offline_app.openapi_schema
    assert "/internal/payment-events" not in committed["paths"]


def test_new_route_model_query_and_roles_come_from_code(offline_app, monkeypatch, tmp_path):
    class Probe(Dto):
        value: str = Field(min_length=3)

    @offline_app.get(
        "/api/export-probe",
        response_model=Probe,
        operation_id="export_probe",
        dependencies=[Depends(require_roles(Role.HEAD))],
    )
    def probe(limit: Annotated[int, Query(ge=2, le=5)]):
        return {"value": "probe"}

    metadata = json.loads(openapi.METADATA.read_text(encoding="utf-8"))
    metadata["operations"]["export_probe"] = {"x-requirements": []}
    target = tmp_path / "metadata.json"
    target.write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(openapi, "METADATA", target)
    document = offline_app.openapi()
    operation = document["paths"]["/api/export-probe"]["get"]
    assert operation["x-roles"] == ["head"]
    assert operation["parameters"][0]["schema"]["minimum"] == 2
    assert operation["parameters"][0]["schema"]["maximum"] == 5
    assert document["components"]["schemas"]["Probe"]["properties"]["value"]["minLength"] == 3


@pytest.mark.parametrize("name", ["Client", "ClientCreate", "ClientUpdate"])
def test_contact_rule_is_composed_without_splitting_object(offline_app, name):
    document = offline_app.openapi()
    schema = document["components"]["schemas"][name]
    assert "anyOf" not in schema
    assert "full_name" in schema["properties"]
    assert "anyOf" in schema["allOf"][0]
    example = schema["examples"][0]
    validator = Draft202012Validator({**schema, "components": document["components"]})
    assert not validator.is_valid({**example, "phone": None, "email": None})
    assert validator.is_valid({**example, "phone": "+79990000001", "email": None})


def test_validation_responses_and_named_types_match_implemented_contract(offline_app):
    document = offline_app.openapi()
    schemas = document["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    for path in document["paths"].values():
        for operation in path.values():
            assert operation["x-implementation-status"] == "implemented"
            if "422" in operation["responses"]:
                assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
                    "$ref": "#/components/schemas/Error"
                }
    assert schemas["PaymentStatus"]["enum"] == ["pending", "succeeded", "failed"]
    assert not Draft202012Validator(schemas["PositiveMoney"]).is_valid("0.00")


def test_check_rejects_stale_export(offline_app, monkeypatch, tmp_path):
    source = ROOT / "docs/api/build_openapi.py"
    spec = importlib.util.spec_from_file_location("export_check", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    document = offline_app.openapi()
    monkeypatch.setattr(module, "build", lambda: document)
    monkeypatch.setattr(module, "DIRECTORY", tmp_path)
    monkeypatch.setattr("sys.argv", [str(source), "--check"])
    stale = {**document, "info": {**document["info"], "title": "stale"}}
    (tmp_path / "openapi.json").write_text(json.dumps(stale), encoding="utf-8")
    with pytest.raises(SystemExit, match="OpenAPI is stale"):
        module.main()
