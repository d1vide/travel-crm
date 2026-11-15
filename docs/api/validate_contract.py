# /// script
# requires-python = ">=3.12"
# dependencies = ["jsonschema==4.26.0", "openapi-spec-validator==0.9.0"]
# ///
"""Validate the proposed domain schema, examples and status vocabulary."""

import copy
import json
import re
from datetime import datetime
from pathlib import Path

from build_openapi import build
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate as validate_openapi


def main() -> None:
    directory = Path(__file__).resolve().parent
    schema = json.loads((directory / "domain.schema.json").read_text(encoding="utf-8"))
    examples = json.loads(
        (directory / "domain.examples.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    if examples["contract_version"] != schema["x-contract-version"]:
        raise ValueError("Schema and example versions differ")

    checker = FormatChecker()

    @checker.checks("date-time", raises=ValueError)
    def is_utc_timestamp(value: object) -> bool:
        if not isinstance(value, str):
            return True  # JSON Schema's type keyword handles non-strings.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value):
            return False
        return datetime.fromisoformat(value).utcoffset().total_seconds() == 0

    validated = set()
    for example in examples["examples"]:
        name = example["schema"]
        if name in validated or name not in schema["$defs"]:
            raise ValueError(f"Duplicate or unknown example schema: {name}")
        validator = Draft202012Validator(
            {"$ref": f"#/$defs/{name}", "$defs": schema["$defs"]},
            format_checker=checker,
        )
        validator.validate(example["value"])
        validated.add(name)

    object_names = {
        name
        for name, definition in schema["$defs"].items()
        if definition.get("type") == "object"
    }
    if object_names - validated:
        raise ValueError(f"Missing object examples: {sorted(object_names - validated)}")

    examples_by_name = {
        example["schema"]: example["value"] for example in examples["examples"]
    }
    invalid_examples = [
        ("Money", 100.0),
        ("Money", "-1.00"),
        ("Money", "1.001"),
        ("Money", "01.00"),
        ("PositiveMoney", "0.00"),
        ("Role", "admin"),
        ("Timestamp", "2026-11-15T09:00:00+03:00"),
        ("Date", "2026-02-30"),
    ]
    for name, changes in [
        ("Client", {"phone": None, "email": None}),
        ("PublicSelection", {"client_id": "private"}),
        ("PublicTouristForm", {"document_number": "private"}),
        ("FinancialBooking", {"full_name": "private"}),
        ("User", {"password_hash": "private"}),
        ("TouristSnapshot", {"document_type": "international_passport"}),
        ("Request", {"tourist_count": 0}),
        ("Error", {"fields": [{"field": "x"}]}),
        ("Error", {"code": "invented_error_code"}),
        ("RequestCreate", {"status": "booked"}),
        ("PaymentCreate", {"amount": 100}),
    ]:
        value = copy.deepcopy(examples_by_name[name])
        value.update(changes)
        invalid_examples.append((name, value))
    for name, value in invalid_examples:
        validator = Draft202012Validator(
            {"$ref": f"#/$defs/{name}", "$defs": schema["$defs"]},
            format_checker=checker,
        )
        if validator.is_valid(value):
            raise ValueError(f"Invalid {name} example unexpectedly accepted")

    for name, edges in schema["x-state-transitions"].items():
        statuses = set(schema["$defs"][name]["enum"])
        seen = set()
        for edge in edges:
            if len(edge) != 2:
                raise ValueError(f"Invalid transition: {name}: {edge}")
            before, after = edge
            if (before is not None and before not in statuses) or after not in statuses:
                raise ValueError(f"Unknown status: {name}: {edge}")
            if tuple(edge) in seen:
                raise ValueError(f"Duplicate transition: {name}: {edge}")
            seen.add(tuple(edge))

    # Keep the human-readable transition matrix and machine vocabulary aligned.
    sections = {
        "## Заявка": "RequestStatus",
        "## Бронь": "BookingStatus",
        "## Платёж": "PaymentStatus",
        "## Возврат": "RefundStatus",
    }
    documented = {name: set() for name in sections.values()}
    current = None
    for line in (
        (directory.parent / "state-transitions.md")
        .read_text(encoding="utf-8")
        .splitlines()
    ):
        if line.startswith("## "):
            current = sections.get(line)
        if current and line.startswith("|"):
            columns = [column.strip() for column in line.strip("|").split("|")]
            if len(columns) < 4:
                continue
            targets = re.findall(r"`([^`]+)`", columns[1])
            if len(targets) != 1 or targets[0] not in schema["$defs"][current]["enum"]:
                continue
            sources = re.findall(r"`([^`]+)`", columns[0])
            for source in sources or [None]:
                documented[current].add((source, targets[0]))
    for name, edges in schema["x-state-transitions"].items():
        if documented[name] != {tuple(edge) for edge in edges}:
            raise ValueError(f"Markdown and machine transitions differ: {name}")

    spec = json.loads((directory / "openapi.json").read_text(encoding="utf-8"))
    if spec != build():
        raise ValueError("OpenAPI is stale; run build_openapi.py")
    validate_openapi(spec)
    if spec["info"]["version"] != schema["x-contract-version"]:
        raise ValueError("OpenAPI and domain versions differ")

    def resolve(value):
        while isinstance(value, dict) and "$ref" in value:
            path = value["$ref"]
            if not path.startswith("#/"):
                raise ValueError(f"External reference in standalone OpenAPI: {path}")
            value = spec
            for part in path[2:].split("/"):
                value = value[part.replace("~1", "/").replace("~0", "~")]
        return value

    def check_media(content):
        media = content.get("application/json")
        if media and "example" in media:
            Draft202012Validator(
                {"components": spec["components"], **media["schema"]},
                format_checker=checker,
            ).validate(media["example"])

    operation_ids = set()
    requirements = set()
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            operation_id = operation["operationId"]
            if operation_id in operation_ids:
                raise ValueError(f"Duplicate operationId: {operation_id}")
            operation_ids.add(operation_id)
            requirements.update(operation["x-requirements"])
            roles = operation["x-roles"]
            if "public" in roles and operation.get("security") != []:
                raise ValueError(
                    f"Public route unexpectedly requires a session: {path}"
                )
            if (
                "accountant" in roles
                and not path.startswith("/api/auth/")
                and method != "get"
            ):
                raise ValueError(f"Accountant may mutate business data: {path}")
            for response in operation["responses"].values():
                check_media(resolve(response).get("content", {}))
            if "requestBody" in operation:
                check_media(operation["requestBody"]["content"])
    if requirements != {f"FR-{number:02d}" for number in range(1, 14)}:
        raise ValueError("OpenAPI does not cover exactly FR-01 through FR-13")

    for name in ("README.md", "frontend-review.md"):
        for target in re.findall(
            r"\]\(([^)]+)\)", (directory / name).read_text(encoding="utf-8")
        ):
            if (
                "://" not in target
                and not target.startswith("#")
                and not (directory / target.split("#")[0]).exists()
            ):
                raise ValueError(f"Broken documentation link: {name}: {target}")

    print(
        f"Valid Draft 2020-12 schema; {len(schema['$defs'])} definitions; "
        f"{len(validated)} examples; {len(invalid_examples)} invalid examples rejected; "
        f"{len(operation_ids)} OpenAPI operations; FR-01..13, permissions, transitions and links checked."
    )


if __name__ == "__main__":
    main()
