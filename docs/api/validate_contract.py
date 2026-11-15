# /// script
# requires-python = ">=3.12"
# dependencies = ["jsonschema==4.26.0"]
# ///
"""Validate the proposed domain schema, examples and status vocabulary."""

import json
import re
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def main() -> None:
    directory = Path(__file__).resolve().parent
    schema = json.loads((directory / "domain.schema.json").read_text(encoding="utf-8"))
    examples = json.loads((directory / "domain.examples.json").read_text(encoding="utf-8"))
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
        name for name, definition in schema["$defs"].items()
        if definition.get("type") == "object"
    }
    if object_names - validated:
        raise ValueError(f"Missing object examples: {sorted(object_names - validated)}")

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

    print(
        f"Valid Draft 2020-12 schema; {len(schema['$defs'])} definitions; "
        f"{len(validated)} examples; status transitions checked."
    )


if __name__ == "__main__":
    main()
