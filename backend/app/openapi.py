"""Public HTTP contract generated from registered routes and Pydantic models."""

import copy
import json
from pathlib import Path

from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute, iter_route_contexts

METADATA = Path(__file__).with_name("api_metadata.json")
ALIASES = {"UserDto": "User", "UserProfileDto": "UserProfile"}


def dependency_roles(dependant):
    for dependency in dependant.dependencies:
        roles = getattr(dependency.call, "allowed_roles", None)
        if roles is not None:
            return list(roles)
        roles = dependency_roles(dependency)
        if roles is not None:
            return roles
    return None


def build_openapi(application):
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    document = get_openapi(
        title=metadata["info"]["title"],
        version=metadata["info"]["version"],
        description=metadata["info"]["description"],
        routes=application.routes,
        openapi_version="3.1.1",
    )
    document["servers"] = [{"url": "/"}]
    document["x-implementation-status"] = "implemented"
    schemas = document["components"]["schemas"]
    # Stable public type names also used independently by frontend forms.
    # Their definitions come from model fields, never from a second schema registry.
    field_aliases = {
        "Id": ("Client", "id"),
        "Money": ("Payment", "amount"),
        "PositiveMoney": ("PaymentCreate", "amount"),
        "Date": ("TourOffer", "starts_on"),
        "Timestamp": ("Client", "created_at"),
        "RequestAction": ("Request", "allowed_actions"),
        "BookingAction": ("Booking", "allowed_actions"),
        "PaymentAction": ("Payment", "allowed_actions"),
        "RefundAction": ("Refund", "allowed_actions"),
        "PaymentStatus": ("Payment", "status"),
        "RefundStatus": ("Refund", "status"),
        "DocumentType": ("Tourist", "document_type"),
        "PublicLinkPurpose": ("PublicLinkInfo", "purpose"),
    }
    for name, (model, field) in field_aliases.items():
        definition = schemas[model]["properties"][field]
        schemas[name] = copy.deepcopy(definition.get("items", definition))
    for name, annotation in metadata["schemas"].items():
        source = next((key for key, alias in ALIASES.items() if alias == name), name)
        if source in schemas:
            schemas[source].update(copy.deepcopy(annotation))

    seen = set()
    for route in iter_route_contexts(application.routes):
        if not isinstance(route.original_route, APIRoute) or not route.include_in_schema:
            continue
        for method in route.methods:
            operation = document["paths"][route.path_format][method.lower()]
            operation_id = operation["operationId"]
            if operation_id in seen:
                raise ValueError(f"Duplicate operationId: {operation_id}")
            seen.add(operation_id)
            if operation_id not in metadata["operations"]:
                raise ValueError(f"Missing operation metadata: {operation_id}")
            annotation = metadata["operations"][operation_id]
            for key in ("summary", "description", "x-requirements"):
                if key in annotation:
                    operation[key] = annotation[key]
            operation["x-implementation-status"] = "implemented"
            roles = dependency_roles(route.dependant)
            operation["x-roles"] = roles or (
                ["manager", "head", "accountant"] if operation.get("security") else ["public"]
            )
            if not operation.get("security"):
                operation["security"] = []
            for parameter in operation.get("parameters", []):
                description = annotation.get("parameters", {}).get(
                    parameter["in"] + ":" + parameter["name"]
                )
                if description:
                    parameter["description"] = description
            if "request_example" in annotation:
                operation["requestBody"]["content"]["application/json"]["example"] = annotation[
                    "request_example"
                ]
            # Common handlers use Error, including FastAPI validation failures.
            for code in ("422", "429", "500", "503"):
                if code == "422" and code not in operation["responses"]:
                    continue
                operation["responses"][code] = {
                    "description": {
                        "422": "Validation error",
                        "429": "Rate limited",
                        "500": "Server error",
                        "503": "Service unavailable",
                    }[code],
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
                    },
                }
            for code, response in operation["responses"].items():
                details = annotation.get("responses", {}).get(code, {})
                for key in ("description", "headers"):
                    if key in details:
                        response[key] = details[key]
                if "example" in details and "content" in response:
                    response["content"]["application/json"]["example"] = details["example"]
                if code == "401":
                    response.setdefault("headers", {})["WWW-Authenticate"] = {
                        "schema": {"type": "string"},
                        "description": "Bearer",
                    }
    unused = set(metadata["operations"]) - seen
    if unused:
        raise ValueError(f"Metadata for missing operations: {sorted(unused)}")
    for name in ("HTTPValidationError", "ValidationError"):
        schemas.pop(name, None)

    def rename(value):
        if isinstance(value, list):
            return [rename(item) for item in value]
        if isinstance(value, dict):
            return {ALIASES.get(key, key): rename(item) for key, item in value.items()}
        if isinstance(value, str) and value.startswith("#/components/schemas/"):
            name = value.rsplit("/", 1)[1]
            return "#/components/schemas/" + ALIASES.get(name, name)
        return value

    return rename(document)
