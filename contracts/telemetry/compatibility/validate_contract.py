#!/usr/bin/env python3
"""Validate Junjo's canonical telemetry artifacts without third-party packages."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import string
from datetime import datetime
from pathlib import Path
from typing import Any

from canonical_json import CanonicalizationError
from canonical_json import dumps as canonical_json_dumps
from schema_normalization import (
    SchemaNormalizationError,
    normalize_generated_schema,
)

CONTRACT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = CONTRACT_ROOT / "fixtures"
SCHEMA_ROOT = CONTRACT_ROOT / "schemas"
WORKFLOW_SCENARIOS = {
    "basic_workflow_success",
    "cancelled_executable",
    "failed_executable_with_error_type",
    "hook_failure_on_surrounding_span",
    "run_concurrent_success",
    "subflow_with_parent_store",
}
PAYLOAD_MODES = {"full", "redacted", "excluded", "reference"}
SCHEMAS: dict[str, dict[str, Any]] = {}


class ContractValidationError(ValueError):
    """Raised when a canonical telemetry artifact violates the active contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class DuplicateJsonObjectNameError(ValueError):
    """Raised before Python's JSON decoder can collapse duplicate members."""


class NonPortableJsonValueError(ValueError):
    """Raised when normalized JSON is outside the I-JSON shared domain."""


class PayloadNestingDepthError(ValueError):
    """Raised when normalized JSON exceeds the interoperable nesting bound."""


_SAFE_INTEGER_MAX = 2**53 - 1
_UINT64_MAX = 2**64 - 1
MAX_JSON_NESTING_DEPTH = 128


def _validate_portable_json(value: Any, path: str = "$") -> None:
    pending: list[tuple[Any, str, int]] = [(value, path, 0)]
    while pending:
        current, current_path, depth = pending.pop()
        if depth > MAX_JSON_NESTING_DEPTH:
            raise PayloadNestingDepthError(
                f"JSON nesting exceeds {MAX_JSON_NESTING_DEPTH} at {current_path}"
            )
        if current is None or isinstance(current, bool):
            continue
        if isinstance(current, int):
            if not -_SAFE_INTEGER_MAX <= current <= _SAFE_INTEGER_MAX:
                raise NonPortableJsonValueError(f"unsafe integer at {current_path}")
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise NonPortableJsonValueError(f"non-finite number at {current_path}")
            continue
        if isinstance(current, str):
            try:
                current.encode("utf-8")
            except UnicodeEncodeError as error:
                raise NonPortableJsonValueError(
                    f"invalid Unicode string at {current_path}"
                ) from error
            continue
        if isinstance(current, list):
            pending.extend(
                (item, f"{current_path}[{index}]", depth + 1)
                for index, item in enumerate(current)
            )
            continue
        if isinstance(current, dict):
            for key, item in current.items():
                pending.append((key, f"{current_path}.<key>", depth + 1))
                pending.append((item, f"{current_path}.{key}", depth + 1))
            continue
        raise NonPortableJsonValueError(f"unsupported JSON value at {current_path}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateJsonObjectNameError(key)
        value[key] = item
    return value


def _decode_json(
    raw: str,
    invalid_code: str,
    context: str,
    *,
    enforce_portable: bool = False,
) -> Any:
    try:
        try:
            value = json.loads(
                raw,
                parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
                object_pairs_hook=_strict_object,
            )
        except RecursionError as error:
            raise PayloadNestingDepthError(
                f"JSON nesting exceeds {MAX_JSON_NESTING_DEPTH}"
            ) from error
        if enforce_portable:
            _validate_portable_json(value)
        return value
    except DuplicateJsonObjectNameError as error:
        raise ContractValidationError(
            "duplicate_json_object_name",
            f"{context}: duplicate object name {error}",
        ) from error
    except NonPortableJsonValueError as error:
        raise ContractValidationError(
            "nonportable_json_value",
            f"{context}: {error}",
        ) from error
    except PayloadNestingDepthError as error:
        raise ContractValidationError(
            "payload_nesting_too_deep",
            f"{context}: {error}",
        ) from error
    except (json.JSONDecodeError, ValueError) as error:
        raise ContractValidationError(invalid_code, f"{context}: {error}") from error


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ContractValidationError(code, message)


def _is_lower_hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in string.hexdigits.lower() for character in value)
        and value == value.lower()
    )


def _is_portable_text(value: Any, *, nonempty: bool = False) -> bool:
    if not isinstance(value, str) or (nonempty and not value):
        return False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return True


def _load_json(path: Path) -> Any:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ContractValidationError("invalid_json", f"{path}: {error}") from error
    return _decode_json(raw, "invalid_json", str(path), enforce_portable=True)


def _structural_digest(prefix: str, material: dict[str, Any]) -> str:
    try:
        canonical = canonical_json_dumps(material)
    except CanonicalizationError as error:
        raise ContractValidationError(
            "invalid_structural_material",
            f"{prefix} material is outside the RFC 8785 I-JSON domain: {error}",
        ) from error
    return f"{prefix}_sha256:{hashlib.sha256(canonical).hexdigest()}"


def _schema_type_matches(instance: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(instance, dict)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "integer":
        return type(instance) is int
    if expected == "boolean":
        return type(instance) is bool
    if expected == "null":
        return instance is None
    raise ContractValidationError("unsupported_schema_keyword", f"type {expected!r}")


def _resolve_schema_reference(
    reference: str,
    root_schema: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if reference.startswith("#"):
        target_root = root_schema
        fragment = reference[1:]
    else:
        file_name, separator, fragment = reference.partition("#")
        _require(file_name in SCHEMAS, "invalid_schema_reference", reference)
        target_root = SCHEMAS[file_name]
        fragment = fragment if separator else ""
    target: Any = target_root
    if fragment:
        _require(fragment.startswith("/"), "invalid_schema_reference", reference)
        for token in fragment[1:].split("/"):
            decoded = _decode_pointer_token(token)
            _require(isinstance(target, dict) and decoded in target, "invalid_schema_reference", reference)
            target = target[decoded]
    _require(isinstance(target, dict), "invalid_schema_reference", reference)
    return target, target_root


def _schema_matches(instance: Any, schema: Any, root_schema: dict[str, Any]) -> bool:
    if schema is True:
        return True
    if schema is False or not isinstance(schema, dict):
        return False
    if "$ref" in schema:
        target, target_root = _resolve_schema_reference(schema["$ref"], root_schema)
        return _schema_matches(instance, target, target_root)
    if "oneOf" in schema:
        choices = schema["oneOf"]
        return isinstance(choices, list) and sum(
            _schema_matches(instance, choice, root_schema) for choice in choices
        ) == 1
    if "type" in schema:
        expected_types = schema["type"]
        if isinstance(expected_types, str):
            expected_types = [expected_types]
        if not isinstance(expected_types, list) or not any(
            isinstance(expected, str) and _schema_type_matches(instance, expected)
            for expected in expected_types
        ):
            return False
    if "const" in schema and (
        type(instance) is not type(schema["const"]) or instance != schema["const"]
    ):
        return False
    if "enum" in schema and not any(
        type(instance) is type(choice) and instance == choice for choice in schema["enum"]
    ):
        return False
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            return False
        pattern = schema.get("pattern")
        if pattern is not None and (not isinstance(pattern, str) or re.search(pattern, instance) is None):
            return False
        if schema.get("format") == "date-time":
            if re.fullmatch(
                r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})",
                instance,
            ) is None:
                return False
            try:
                parsed = datetime.fromisoformat(
                    instance.replace("Z", "+00:00").replace("z", "+00:00")
                )
            except ValueError:
                return False
            if parsed.tzinfo is None:
                return False
    if type(instance) is int and instance < schema.get("minimum", instance):
        return False
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            return False
        item_schema = schema.get("items")
        if item_schema is not None and not all(
            _schema_matches(item, item_schema, root_schema) for item in instance
        ):
            return False
    if isinstance(instance, dict):
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(key in instance for key in required):
            return False
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return False
        for key, property_schema in properties.items():
            if key in instance and not _schema_matches(instance[key], property_schema, root_schema):
                return False
        extras = set(instance) - set(properties)
        additional = schema.get("additionalProperties", True)
        if additional is False and extras:
            return False
        if isinstance(additional, dict) and not all(
            _schema_matches(instance[key], additional, root_schema) for key in extras
        ):
            return False
    return True


def _validate_schema_instance(
    instance: Any,
    schema_name: str,
    code: str,
    context: str,
) -> None:
    _require(schema_name in SCHEMAS, "missing_schema", schema_name)
    _require(_schema_matches(instance, SCHEMAS[schema_name], SCHEMAS[schema_name]), code, context)


def _audit_schema_definition(schema: Any, path: str) -> None:
    if isinstance(schema, bool):
        return
    _require(isinstance(schema, dict), "invalid_schema_definition", path)
    allowed = {
        "$schema",
        "$id",
        "$ref",
        "$defs",
        "title",
        "description",
        "type",
        "required",
        "properties",
        "additionalProperties",
        "const",
        "enum",
        "oneOf",
        "items",
        "minItems",
        "minLength",
        "minimum",
        "pattern",
        "format",
    }
    unknown = set(schema) - allowed
    _require(
        not unknown,
        "unsupported_schema_keyword",
        f"{path}: {sorted(unknown)}",
    )
    for container_name in ("$defs", "properties"):
        container = schema.get(container_name, {})
        _require(isinstance(container, dict), "invalid_schema_definition", path)
        for name, child in container.items():
            _audit_schema_definition(child, f"{path}/{container_name}/{name}")
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        _audit_schema_definition(additional, f"{path}/additionalProperties")
    if "items" in schema:
        _audit_schema_definition(schema["items"], f"{path}/items")
    for index, child in enumerate(schema.get("oneOf", [])):
        _audit_schema_definition(child, f"{path}/oneOf/{index}")


def _validate_schema_evaluator_guard() -> None:
    try:
        _audit_schema_definition({"type": "integer", "maximum": 1}, "mutation-probe")
    except ContractValidationError as error:
        _require(
            error.code == "unsupported_schema_keyword",
            "schema_guard_failure",
            "unsupported keyword probe",
        )
    else:
        raise ContractValidationError(
            "schema_guard_failure", "unsupported assertion keyword was accepted"
        )
    _require(
        not _schema_matches(
            "2026-07-14 00:00:00+00:00",
            {"type": "string", "format": "date-time"},
            {},
        ),
        "schema_guard_failure",
        "non-RFC3339 date-time mutation was accepted",
    )


def _decode_pointer_token(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def _pointer_tokens(pointer: object, fixture_name: str) -> list[str]:
    _require(isinstance(pointer, str), "invalid_state_patch", f"{fixture_name}: pointer")
    _require(pointer == "" or pointer.startswith("/"), "invalid_state_patch", fixture_name)
    if pointer == "":
        return []
    return [_decode_pointer_token(token) for token in pointer[1:].split("/")]


def _array_index(token: str, length: int, *, allow_end: bool, fixture_name: str) -> int:
    _require(token != "-" or allow_end, "invalid_state_patch", fixture_name)
    if token == "-":
        return length
    _require(token.isdigit(), "invalid_state_patch", fixture_name)
    _require(token == "0" or not token.startswith("0"), "invalid_state_patch", fixture_name)
    index = int(token)
    upper = length if allow_end else length - 1
    _require(0 <= index <= upper, "invalid_state_patch", fixture_name)
    return index


def _pointer_value(document: Any, pointer: object, fixture_name: str) -> Any:
    current = document
    for token in _pointer_tokens(pointer, fixture_name):
        if isinstance(current, list):
            current = current[
                _array_index(token, len(current), allow_end=False, fixture_name=fixture_name)
            ]
        else:
            _require(isinstance(current, dict) and token in current, "invalid_state_patch", fixture_name)
            current = current[token]
    return current


def _pointer_parent(document: Any, pointer: object, fixture_name: str) -> tuple[Any, str]:
    tokens = _pointer_tokens(pointer, fixture_name)
    _require(bool(tokens), "invalid_state_patch", f"{fixture_name}: root has no parent")
    parent = document
    for token in tokens[:-1]:
        if isinstance(parent, list):
            parent = parent[
                _array_index(token, len(parent), allow_end=False, fixture_name=fixture_name)
            ]
        else:
            _require(isinstance(parent, dict) and token in parent, "invalid_state_patch", fixture_name)
            parent = parent[token]
    return parent, tokens[-1]


def _remove_pointer(document: Any, pointer: object, fixture_name: str) -> Any:
    tokens = _pointer_tokens(pointer, fixture_name)
    if not tokens:
        return None
    parent, token = _pointer_parent(document, pointer, fixture_name)
    if isinstance(parent, list):
        del parent[_array_index(token, len(parent), allow_end=False, fixture_name=fixture_name)]
    else:
        _require(isinstance(parent, dict) and token in parent, "invalid_state_patch", fixture_name)
        del parent[token]
    return document


def _add_pointer(document: Any, pointer: object, value: Any, fixture_name: str) -> Any:
    tokens = _pointer_tokens(pointer, fixture_name)
    if not tokens:
        return copy.deepcopy(value)
    parent, token = _pointer_parent(document, pointer, fixture_name)
    value = copy.deepcopy(value)
    if isinstance(parent, list):
        parent.insert(
            _array_index(token, len(parent), allow_end=True, fixture_name=fixture_name), value
        )
    else:
        _require(isinstance(parent, dict), "invalid_state_patch", fixture_name)
        parent[token] = value
    return document


def _replace_pointer(document: Any, pointer: object, value: Any, fixture_name: str) -> Any:
    tokens = _pointer_tokens(pointer, fixture_name)
    if not tokens:
        return copy.deepcopy(value)
    parent, token = _pointer_parent(document, pointer, fixture_name)
    value = copy.deepcopy(value)
    if isinstance(parent, list):
        parent[_array_index(token, len(parent), allow_end=False, fixture_name=fixture_name)] = value
    else:
        _require(isinstance(parent, dict) and token in parent, "invalid_state_patch", fixture_name)
        parent[token] = value
    return document


def _apply_patch(document: Any, operations: list[dict[str, Any]], fixture_name: str) -> Any:
    result = copy.deepcopy(document)
    for operation in operations:
        _require(isinstance(operation, dict), "invalid_state_patch", f"{fixture_name}: patch item")
        op = operation.get("op")
        path = operation.get("path")
        try:
            if op == "add":
                _require("value" in operation, "invalid_state_patch", fixture_name)
                result = _add_pointer(result, path, operation["value"], fixture_name)
            elif op == "replace":
                _require("value" in operation, "invalid_state_patch", fixture_name)
                result = _replace_pointer(result, path, operation["value"], fixture_name)
            elif op == "remove":
                result = _remove_pointer(result, path, fixture_name)
            elif op == "copy":
                _require("from" in operation, "invalid_state_patch", fixture_name)
                value = copy.deepcopy(_pointer_value(result, operation["from"], fixture_name))
                result = _add_pointer(result, path, value, fixture_name)
            elif op == "move":
                _require("from" in operation, "invalid_state_patch", fixture_name)
                from_tokens = _pointer_tokens(operation["from"], fixture_name)
                path_tokens = _pointer_tokens(path, fixture_name)
                _require(
                    path_tokens[: len(from_tokens)] != from_tokens or path_tokens == from_tokens,
                    "invalid_state_patch",
                    f"{fixture_name}: cannot move a value into its child",
                )
                value = copy.deepcopy(_pointer_value(result, operation["from"], fixture_name))
                result = _remove_pointer(result, operation["from"], fixture_name)
                result = _add_pointer(result, path, value, fixture_name)
            elif op == "test":
                _require("value" in operation, "invalid_state_patch", fixture_name)
                _require(
                    _pointer_value(result, path, fixture_name) == operation["value"],
                    "patch_test_failed",
                    fixture_name,
                )
            else:
                raise ContractValidationError(
                    "invalid_state_patch", f"{fixture_name}: unsupported patch op {op!r}"
                )
        except ContractValidationError:
            raise
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise ContractValidationError(
                "patch_replay_mismatch", f"{fixture_name}: {error}"
            ) from error
    return result


def _validate_payload_slot(attributes: dict[str, Any], root: str, fixture_name: str) -> Any | None:
    mode = attributes.get(f"{root}.mode")
    policy = attributes.get(f"{root}.policy")
    _require(
        f"{root}.mode" in attributes and f"{root}.policy" in attributes,
        "required_payload_slot_missing",
        f"{fixture_name}: {root}",
    )
    _require(
        _is_portable_text(mode, nonempty=True) and mode in PAYLOAD_MODES,
        "invalid_payload_slot",
        f"{fixture_name}: {root}.mode",
    )
    _require(
        _is_portable_text(policy, nonempty=True),
        "invalid_payload_slot",
        f"{fixture_name}: {root}.policy",
    )
    content_present = root in attributes
    reference_present = f"{root}.reference" in attributes
    if mode in {"full", "redacted"}:
        _require(content_present and not reference_present, "invalid_payload_slot", f"{fixture_name}: {root}")
        raw = attributes[root]
        _require(isinstance(raw, str), "invalid_payload_slot", f"{fixture_name}: {root}")
        return _decode_json(
            raw,
            "invalid_payload_json",
            f"{fixture_name}: {root}",
            enforce_portable=True,
        )
    if mode == "reference":
        _require(not content_present and reference_present, "invalid_payload_slot", f"{fixture_name}: {root}")
        _require(
            _is_portable_text(attributes[f"{root}.reference"], nonempty=True),
            "invalid_payload_slot",
            f"{fixture_name}: {root}.reference",
        )
    else:
        _require(not content_present and not reference_present, "invalid_payload_slot", f"{fixture_name}: {root}")
    return None


def _payload_slot_present(attributes: dict[str, Any], root: str) -> bool:
    """Return whether any member of one payload slot was emitted."""
    return any(
        key in attributes
        for key in (root, f"{root}.mode", f"{root}.policy", f"{root}.reference")
    )


def _candidate_present(attributes: dict[str, Any], root: str) -> bool:
    """Return whether any availability, reason, or payload member was emitted."""
    return _payload_slot_present(attributes, root) or any(
        key in attributes for key in (f"{root}.available", f"{root}.unavailable_reason")
    )


def _require_payload_slot_absent(
    attributes: dict[str, Any],
    root: str,
    code: str,
    fixture_name: str,
) -> None:
    _require(not _payload_slot_present(attributes, root), code, fixture_name)


def _operation_outcome(span: dict[str, Any]) -> str:
    attributes = span["attributes_json"]
    if attributes.get("junjo.cancelled") is True:
        return "cancelled"
    if span.get("status_code") == "2" or "error.type" in attributes:
        return "failed"
    return "completed"


def _validate_graph_snapshot(raw_snapshot: object, fixture_name: str) -> None:
    _require(isinstance(raw_snapshot, str), "invalid_graph_snapshot", fixture_name)
    snapshot = _decode_json(
        raw_snapshot,
        "invalid_graph_snapshot",
        fixture_name,
        enforce_portable=True,
    )
    _validate_schema_instance(
        snapshot,
        "execution-graph-snapshot.v2.schema.json",
        "invalid_graph_snapshot",
        fixture_name,
    )
    _require(snapshot.get("v") == 2, "invalid_graph_snapshot", fixture_name)
    _require(bool(snapshot.get("graphStructuralId")), "invalid_graph_snapshot", fixture_name)
    _require(isinstance(snapshot.get("nodes"), list), "invalid_graph_snapshot", fixture_name)
    _require(isinstance(snapshot.get("edges"), list), "invalid_graph_snapshot", fixture_name)


def _validate_common_fixture(fixture: Any, name: str, contract_version: int) -> None:
    _require(isinstance(fixture, dict), "invalid_fixture_root", name)
    _require(fixture.get("contract_version") == contract_version, "wrong_contract_version", name)
    _require(fixture.get("scenario") == name, "scenario_mismatch", name)
    _require(_is_lower_hex(fixture.get("trace_id"), 32), "invalid_trace_id", name)
    _require(
        _is_portable_text(fixture.get("service_name"), nonempty=True),
        "missing_service_name",
        name,
    )
    _require(isinstance(fixture.get("spans"), list) and fixture["spans"], "missing_spans", name)

    span_ids: set[str] = set()
    store_names: dict[str, str] = {}
    for span in fixture["spans"]:
        _require(isinstance(span, dict), "invalid_span", name)
        _require(span.get("trace_id") == fixture["trace_id"], "trace_id_mismatch", name)
        _require(_is_lower_hex(span.get("span_id"), 16), "invalid_span_id", name)
        _require(span["span_id"] not in span_ids, "duplicate_span_id", name)
        span_ids.add(span["span_id"])
        parent_id = span.get("parent_span_id")
        _require(parent_id is None or _is_lower_hex(parent_id, 16), "invalid_parent_span_id", name)
        _require(span.get("service_name") == fixture["service_name"], "service_name_mismatch", name)
        _require(
            _is_portable_text(span.get("name"), nonempty=True),
            "invalid_span",
            name,
        )
        _require(
            _is_portable_text(span.get("status_message", "")),
            "invalid_span",
            name,
        )
        try:
            start_time = datetime.fromisoformat(
                span["start_time"].replace("Z", "+00:00").replace("z", "+00:00")
            )
            end_time = datetime.fromisoformat(
                span["end_time"].replace("Z", "+00:00").replace("z", "+00:00")
            )
        except (AttributeError, KeyError, ValueError) as error:
            raise ContractValidationError("invalid_span_interval", name) from error
        _require(end_time >= start_time, "invalid_span_interval", name)
        resource = span.get("resource_attributes_json")
        _require(isinstance(resource, dict), "missing_resource_attributes", name)
        _require(resource.get("service.name") == span["service_name"], "resource_service_mismatch", name)
        _require(
            _is_portable_text(resource.get("service.name"), nonempty=True),
            "resource_service_mismatch",
            name,
        )
        if "service.namespace" in resource:
            _require(
                _is_portable_text(resource["service.namespace"]),
                "resource_service_mismatch",
                name,
            )
        if "service.version" in resource:
            _require(
                _is_portable_text(resource["service.version"], nonempty=True),
                "resource_service_mismatch",
                name,
            )
        for field in (
            "resource_dropped_attributes_count",
            "dropped_attributes_count",
            "dropped_events_count",
            "dropped_links_count",
        ):
            value = span.get(field)
            _require(
                type(value) is int and 0 <= value <= _SAFE_INTEGER_MAX,
                "invalid_loss_counter",
                f"{name}: {field}",
            )
        _require(isinstance(span.get("attributes_json"), dict), "invalid_attributes", name)
        _require(isinstance(span.get("events_json"), list), "invalid_events", name)
        _require(isinstance(span.get("links_json"), list), "invalid_links", name)
        for event in span["events_json"]:
            _require(isinstance(event, dict), "invalid_event", name)
            _require(isinstance(event.get("name"), str) and event["name"], "invalid_event", name)
            event_time = event.get("timeUnixNano")
            _require(
                isinstance(event_time, str)
                and re.fullmatch(r"(?:0|[1-9][0-9]{0,19})", event_time) is not None
                and int(event_time) <= _UINT64_MAX,
                "invalid_event",
                name,
            )
            _require(isinstance(event.get("attributes"), dict), "invalid_event", name)
            if event.get("name") == "set_state":
                event_attributes = event["attributes"]
                event_id = event_attributes.get("id")
                store_name = event_attributes.get("junjo.store.name")
                store_id = event_attributes.get("junjo.store.id")
                action = event_attributes.get("junjo.store.action")
                _require(
                    _is_portable_text(event_id, nonempty=True),
                    "missing_transition_event_id",
                    name,
                )
                _require(
                    _is_portable_text(store_name, nonempty=True),
                    "invalid_store_name",
                    name,
                )
                _require(
                    _is_portable_text(store_id, nonempty=True),
                    "missing_store_id",
                    name,
                )
                _require(
                    _is_portable_text(action, nonempty=True),
                    "missing_transition_action",
                    name,
                )
                prior_name = store_names.setdefault(store_id, store_name)
                _require(prior_name == store_name, "invalid_store_name", name)
            dropped = event.get("droppedAttributesCount")
            _require(
                type(dropped) is int and 0 <= dropped <= _SAFE_INTEGER_MAX,
                "invalid_loss_counter",
                name,
            )
        attributes = span["attributes_json"]
        correlation_type = attributes.get("junjo.correlation.type")
        correlation_id = attributes.get("junjo.correlation.id")
        correlation_present = correlation_type is not None or correlation_id is not None
        _require(
            (correlation_type is None) == (correlation_id is None),
            "incomplete_execution_correlation",
            f"{name}: span {span['span_id']}",
        )
        if correlation_present:
            span_type = attributes.get("junjo.span_type")
            _require(
                isinstance(span_type, str)
                and span_type
                in {"workflow", "subflow", "node", "run_concurrent", "agent"}
                and "junjo.agent.operation_type" not in attributes,
                "execution_correlation_on_non_owner",
                f"{name}: span {span['span_id']}",
            )
            _require(
                _is_portable_text(correlation_type, nonempty=True)
                and _is_portable_text(correlation_id, nonempty=True),
                "invalid_execution_correlation",
                f"{name}: span {span['span_id']}",
            )
        if "junjo.span_type" in attributes or "junjo.agent.operation_type" in attributes:
            _require(
                attributes.get("junjo.telemetry.contract_version") == contract_version,
                "wrong_contract_version",
                f"{name}: span {span['span_id']}",
            )

    for span in fixture["spans"]:
        parent_id = span.get("parent_span_id")
        _require(parent_id is None or parent_id in span_ids, "unknown_parent_span", name)

    spans_by_id = {span["span_id"]: span for span in fixture["spans"]}
    owner_types = {"workflow", "subflow", "node", "run_concurrent", "agent"}
    for span in fixture["spans"]:
        attributes = span["attributes_json"]
        span_type = attributes.get("junjo.span_type")
        if not isinstance(span_type, str) or span_type not in owner_types:
            continue
        actual = (
            attributes.get("junjo.correlation.type"),
            attributes.get("junjo.correlation.id"),
        )
        parent_id = span.get("parent_span_id")
        while parent_id is not None:
            ancestor = spans_by_id[parent_id]
            ancestor_attributes = ancestor["attributes_json"]
            inherited = (
                ancestor_attributes.get("junjo.correlation.type"),
                ancestor_attributes.get("junjo.correlation.id"),
            )
            if inherited != (None, None):
                _require(
                    actual == inherited,
                    "execution_correlation_inheritance_mismatch",
                    f"{name}: span {span['span_id']}",
                )
                break
            parent_id = ancestor.get("parent_span_id")
    _validate_schema_instance(
        fixture,
        "telemetry-fixture.schema.json",
        "invalid_telemetry_fixture",
        name,
    )


def _validate_workflow_fixture(fixture: dict[str, Any], name: str) -> None:
    graph_snapshot_count = 0
    owners: dict[str, dict[str, Any]] = {}
    events_by_store: dict[str, list[dict[str, Any]]] = {}
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for span in fixture["spans"]:
        parent_span_id = span.get("parent_span_id")
        if parent_span_id is not None:
            children_by_parent.setdefault(parent_span_id, []).append(span)

    def completed_executable(span: dict[str, Any]) -> bool:
        attributes = span["attributes_json"]
        return span.get("status_code") not in {2, "2"} and attributes.get("junjo.cancelled") is not True

    def expected_node_count(owner: dict[str, Any]) -> int:
        count = 0
        for child in children_by_parent.get(owner["span_id"], []):
            span_type = child["attributes_json"].get("junjo.span_type")
            if span_type in {"node", "subflow"} and completed_executable(child):
                count += 1
            elif span_type == "run_concurrent" and completed_executable(child):
                count += sum(
                    grandchild["attributes_json"].get("junjo.span_type") in {"node", "subflow"}
                    and completed_executable(grandchild)
                    for grandchild in children_by_parent.get(child["span_id"], [])
                )
        return count

    for span in fixture["spans"]:
        attributes = span["attributes_json"]
        snapshot = attributes.get("junjo.workflow.execution_graph_snapshot")
        if snapshot is not None:
            graph_snapshot_count += 1
            _validate_graph_snapshot(snapshot, name)
            node_count = attributes.get("junjo.workflow.node.count")
            _require(
                type(node_count) is int and node_count >= 0,
                "invalid_workflow_node_count",
                f"{name}: span {span['span_id']}",
            )
            _require(
                node_count == expected_node_count(span),
                "workflow_node_count_mismatch",
                f"{name}: span {span['span_id']}",
            )
        store_id = attributes.get("junjo.workflow.store.id")
        if store_id:
            owners[store_id] = span
        for event in span["events_json"]:
            if event["name"] == "set_state":
                event_store_id = event["attributes"].get("junjo.store.id")
                _require(isinstance(event_store_id, str) and event_store_id, "missing_store_id", name)
                events_by_store.setdefault(event_store_id, []).append(event)
    _require(graph_snapshot_count >= 1, "missing_graph_snapshot", name)

    for store_id, owner in owners.items():
        attributes = owner["attributes_json"]
        start = _validate_payload_slot(attributes, "junjo.workflow.state.start", name)
        end = _validate_payload_slot(attributes, "junjo.workflow.state.end", name)
        _require(start is not None and end is not None, "workflow_state_not_full", name)
        revision_start = attributes.get("junjo.store.revision.start")
        revision_end = attributes.get("junjo.store.revision.end")
        count = attributes.get("junjo.store.transition.count")
        _require(revision_start == 0, "invalid_revision_start", name)
        _require(type(revision_end) is int and revision_end >= 0, "invalid_revision_end", name)
        _require(type(count) is int and count >= 0, "invalid_transition_count", name)
        events = sorted(
            events_by_store.get(store_id, []),
            key=lambda event: event["attributes"].get("junjo.store.transition.sequence", -1),
        )
        sequences = [event["attributes"].get("junjo.store.transition.sequence") for event in events]
        _require(sequences == list(range(1, count + 1)), "transition_sequence_mismatch", name)
        state = start
        revision = revision_start
        for event in events:
            event_attributes = event["attributes"]
            _require(event_attributes.get("junjo.store.revision.before") == revision, "revision_discontinuity", name)
            after = event_attributes.get("junjo.store.revision.after")
            _require(after in {revision, revision + 1}, "revision_discontinuity", name)
            patch = _validate_payload_slot(event_attributes, "junjo.state_json_patch", name)
            _require(isinstance(patch, list), "invalid_state_patch", name)
            state = _apply_patch(state, patch, name)
            revision = after
        _require(revision == revision_end, "terminal_revision_mismatch", name)
        _require(state == end, "patch_replay_mismatch", name)
        _require(attributes.get("junjo.store.reconstructable") is True, "reconstructable_mismatch", name)


def _validate_contiguous_sequence(
    values: list[object], expected_count: int, kind: str, fixture_name: str
) -> None:
    _require(all(type(value) is int for value in values), f"{kind}_sequence_out_of_range", fixture_name)
    integers = [int(value) for value in values]
    _require(len(integers) == len(set(integers)), f"{kind}_sequence_duplicate", fixture_name)
    _require(
        all(1 <= value <= expected_count for value in integers),
        f"{kind}_sequence_out_of_range",
        fixture_name,
    )
    expected = list(range(1, expected_count + 1))
    actual = sorted(integers)
    if actual != expected:
        if actual == list(range(1, len(actual) + 1)):
            raise ContractValidationError(f"{kind}_sequence_missing_trailing", fixture_name)
        raise ContractValidationError(f"{kind}_sequence_gap", fixture_name)


def _store_events(fixture: dict[str, Any], store_id: str) -> list[dict[str, Any]]:
    return [
        event
        for span in fixture["spans"]
        for event in span["events_json"]
        if event["name"] == "set_state" and event["attributes"].get("junjo.store.id") == store_id
    ]


def _validate_agent_store(
    fixture: dict[str, Any], owner_attributes: dict[str, Any], fixture_name: str
) -> tuple[Any, Any]:
    store_id = owner_attributes.get("junjo.agent.store.id")
    _require(isinstance(store_id, str) and store_id, "missing_store_id", fixture_name)
    start = _validate_payload_slot(owner_attributes, "junjo.agent.state.start", fixture_name)
    end = _validate_payload_slot(owner_attributes, "junjo.agent.state.end", fixture_name)
    revision_start = owner_attributes.get("junjo.store.revision.start")
    revision_end = owner_attributes.get("junjo.store.revision.end")
    count = owner_attributes.get("junjo.store.transition.count")
    _require(revision_start == 0, "invalid_revision_start", fixture_name)
    _require(type(revision_end) is int and revision_end >= 0, "invalid_revision_end", fixture_name)
    _require(type(count) is int and count >= 0, "invalid_transition_count", fixture_name)
    events = _store_events(fixture, store_id)
    sequences = [event["attributes"].get("junjo.store.transition.sequence") for event in events]
    _validate_contiguous_sequence(sequences, count, "transition", fixture_name)

    reconstructable_claim = owner_attributes.get("junjo.store.reconstructable")
    _require(isinstance(reconstructable_claim, bool), "reconstructable_mismatch", fixture_name)
    start_mode = owner_attributes.get("junjo.agent.state.start.mode")
    end_mode = owner_attributes.get("junjo.agent.state.end.mode")
    start_policy = owner_attributes.get("junjo.agent.state.start.policy")
    _require(
        end_mode == start_mode
        and owner_attributes.get("junjo.agent.state.end.policy") == start_policy,
        "payload_policy_mismatch",
        fixture_name,
    )
    inline_replay = start_mode in {"full", "redacted"}
    _require(
        inline_replay or start_mode in {"excluded", "reference"},
        "payload_policy_mismatch",
        fixture_name,
    )
    if reconstructable_claim:
        _require(inline_replay, "reconstructable_mismatch", fixture_name)
    revision = revision_start
    state = copy.deepcopy(start) if inline_replay else None
    for event in sorted(events, key=lambda item: item["attributes"]["junjo.store.transition.sequence"]):
        attributes = event["attributes"]
        _require(
            attributes.get("junjo.store.revision.before") == revision,
            "revision_discontinuity",
            fixture_name,
        )
        after = attributes.get("junjo.store.revision.after")
        _require(after in {revision, revision + 1}, "revision_discontinuity", fixture_name)
        patch = _validate_payload_slot(attributes, "junjo.state_json_patch", fixture_name)
        _require(
            attributes.get("junjo.state_json_patch.mode") == start_mode
            and attributes.get("junjo.state_json_patch.policy") == start_policy,
            "payload_policy_mismatch",
            fixture_name,
        )
        if inline_replay:
            _require(isinstance(patch, list), "invalid_state_patch", fixture_name)
            state = _apply_patch(state, patch, fixture_name)
        revision = after
    _require(revision == revision_end, "terminal_revision_mismatch", fixture_name)
    if inline_replay:
        _require(state == end, "patch_replay_mismatch", fixture_name)
    return start, end


def _validate_definition_snapshot(
    definition: Any,
    attributes: dict[str, Any],
    fixture_name: str,
) -> dict[str, Any] | None:
    if attributes.get("junjo.agent.definition_snapshot.mode") != "full":
        return None
    _validate_schema_instance(
        definition,
        "agent-definition-snapshot.v1.schema.json",
        "invalid_definition_snapshot",
        fixture_name,
    )
    tool_names = [tool["name"] for tool in definition["tools"]]
    _require(len(tool_names) == len(set(tool_names)), "duplicate_tool_definition", fixture_name)
    tool_by_name: dict[str, dict[str, Any]] = {}
    structural_tools: list[dict[str, Any]] = []
    request_tools: list[dict[str, Any]] = []
    for tool in definition["tools"]:
        material = {
            "v": 1,
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["inputSchema"],
            "outputSchema": tool["outputSchema"],
        }
        _validate_schema_instance(
            material,
            "tool-structural-material.v1.schema.json",
            "invalid_tool_structural_material",
            fixture_name,
        )
        _require(
            tool["structuralId"] == _structural_digest("tool", material),
            "structural_identity_mismatch",
            fixture_name,
        )
        tool_by_name[tool["name"]] = tool
        structural_tools.append({key: value for key, value in material.items() if key != "v"})
        request_tools.append(
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["inputSchema"],
                "outputSchema": tool["outputSchema"],
            }
        )
    material = {
        "v": 1,
        "agentKey": definition["agentKey"],
        "instructions": definition["instructions"],
        "inputSchema": definition["inputSchema"],
        "model": definition["model"],
        "tools": structural_tools,
        "outputSchema": definition["outputSchema"],
        "limits": definition["limits"],
    }
    _validate_schema_instance(
        material,
        "agent-structural-material.v1.schema.json",
        "invalid_agent_structural_material",
        fixture_name,
    )
    _require(
        definition["structuralId"] == _structural_digest("agent", material),
        "structural_identity_mismatch",
        fixture_name,
    )
    _require(
        definition["agentKey"] == attributes.get("junjo.agent.key")
        and definition["name"] == attributes.get("junjo.agent.name")
        and definition["structuralId"] == attributes.get("junjo.executable_structural_id")
        and definition["limits"]
        == {
            "modelRequests": attributes.get("junjo.agent.limit.model_requests"),
            "toolCalls": attributes.get("junjo.agent.limit.tool_calls"),
        },
        "definition_owner_mismatch",
        fixture_name,
    )
    return {
        "agentKey": definition["agentKey"],
        "instructions": definition["instructions"],
        "requestTools": request_tools,
        "toolByName": tool_by_name,
        "outputSchema": definition["outputSchema"],
    }


def _validate_usage_attribute(
    attributes: dict[str, Any],
    root: str,
    schema_name: str,
    code: str,
    fixture_name: str,
) -> dict[str, Any] | None:
    if root not in attributes:
        return None
    raw = attributes[root]
    _require(isinstance(raw, str), code, fixture_name)
    value = _decode_json(raw, code, fixture_name, enforce_portable=True)
    _validate_schema_instance(value, schema_name, code, fixture_name)
    return value


def _validate_model_operation(
    span: dict[str, Any],
    fixture_name: str,
    definition: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, bool, dict[str, Any] | None]:
    attributes = span["attributes_json"]
    outcome = _operation_outcome(span)
    ordinal = attributes.get("junjo.agent.model_request.ordinal")
    _require(type(ordinal) is int and ordinal >= 1, "model_ordinal_noncontiguous", fixture_name)
    _require(
        type(attributes.get("junjo.agent.model_request.state_revision")) is int,
        "invalid_model_state_revision",
        fixture_name,
    )
    for key in (
        "junjo.agent.model.driver_key",
        "junjo.agent.model.provider",
        "junjo.agent.model.name",
    ):
        _require(
            _is_portable_text(attributes.get(key), nonempty=True),
            "invalid_model_identity",
            fixture_name,
        )
    request = _validate_payload_slot(attributes, "junjo.agent.model.request", fixture_name)
    if attributes.get("junjo.agent.model.request.mode") == "full":
        _validate_schema_instance(
            request,
            "agent-model-request.v1.schema.json",
            "invalid_model_request",
            fixture_name,
        )
        _require(
            request["agentKey"] == attributes.get("junjo.agent.key")
            and request["runId"] == attributes.get("junjo.agent.runtime_id")
            and request["ordinal"] == ordinal,
            "model_request_identity_mismatch",
            fixture_name,
        )
        if definition is not None:
            _require(
                request["agentKey"] == definition["agentKey"]
                and request["instructions"] == definition["instructions"]
                and request["tools"] == definition["requestTools"]
                and request["outputSchema"] == definition["outputSchema"],
                "model_request_definition_mismatch",
                fixture_name,
            )
    available = attributes.get("junjo.agent.model.response_candidate.available")
    _require(type(available) is bool, "invalid_candidate_evidence", fixture_name)
    if available:
        _validate_payload_slot(
            attributes, "junjo.agent.model.response_candidate", fixture_name
        )
        _require(
            "junjo.agent.model.response_candidate.unavailable_reason" not in attributes,
            "invalid_candidate_evidence",
            fixture_name,
        )
    else:
        _require_payload_slot_absent(
            attributes,
            "junjo.agent.model.response_candidate",
            "invalid_candidate_evidence",
            fixture_name,
        )
        _require(
            attributes.get("junjo.agent.model.response_candidate.unavailable_reason")
            in {"not_returned", "cancelled", "not_json_serializable"},
            "invalid_candidate_evidence",
            fixture_name,
        )
    unavailable_reason = attributes.get(
        "junjo.agent.model.response_candidate.unavailable_reason"
    )
    _require(
        (unavailable_reason == "cancelled") == (outcome == "cancelled" and not available),
        "invalid_candidate_transport_correspondence",
        fixture_name,
    )
    response_type = attributes.get("junjo.agent.model.response_type")
    response_present = _payload_slot_present(attributes, "junjo.agent.model.response")
    _require(
        (response_type is not None) == response_present,
        "invalid_model_response_evidence",
        fixture_name,
    )
    _require(
        (outcome == "completed") == response_present,
        "invalid_model_response_transport",
        fixture_name,
    )
    if outcome == "completed":
        _require(available is True, "invalid_candidate_transport_correspondence", fixture_name)
    response: dict[str, Any] | None = None
    response_usage: dict[str, Any] | None = None
    response_occurred = False
    if response_type is not None:
        _require(response_type in {"final_output", "tool_calls"}, "invalid_model_response", fixture_name)
        parsed = _validate_payload_slot(attributes, "junjo.agent.model.response", fixture_name)
        response_occurred = True
        if attributes.get("junjo.agent.model.response.mode") == "full":
            _validate_schema_instance(
                parsed,
                "agent-model-response.v1.schema.json",
                "invalid_model_response",
                fixture_name,
            )
            _require(parsed["type"] == response_type, "invalid_model_response", fixture_name)
            response = parsed
            response_usage = response.get("usage")

    operation_usage = _validate_usage_attribute(
        attributes,
        "junjo.agent.model.usage",
        "model-usage.v1.schema.json",
        "invalid_model_usage",
        fixture_name,
    )
    _require(
        operation_usage is None or response_present,
        "model_usage_without_response",
        fixture_name,
    )
    if response is not None:
        _require(operation_usage == response_usage, "model_usage_mismatch", fixture_name)
    elif not response_occurred:
        _require(operation_usage is None, "model_usage_without_response", fixture_name)

    calls: list[dict[str, Any]] = []
    if response is not None and response_type == "tool_calls":
        calls = response["calls"]
        call_ids = [call["id"] for call in calls]
        _require(len(call_ids) == len(set(call_ids)), "tool_call_identity_duplicate", fixture_name)
    return calls, operation_usage, response_occurred, response


def _validate_tool_operation(
    span: dict[str, Any], fixture_name: str
) -> dict[str, Any]:
    attributes = span["attributes_json"]
    outcome = _operation_outcome(span)
    for key in ("junjo.agent.tool_call.id", "junjo.agent.tool.name", "junjo.agent.tool.structural_id"):
        _require(
            _is_portable_text(attributes.get(key), nonempty=True),
            "invalid_tool_identity",
            fixture_name,
        )
    _require(
        re.fullmatch(
            r"tool_sha256:[0-9a-f]{64}",
            attributes["junjo.agent.tool.structural_id"],
        )
        is not None,
        "invalid_tool_identity",
        fixture_name,
    )
    ordinal = attributes.get("junjo.agent.tool_call.ordinal")
    _require(type(ordinal) is int and ordinal >= 1, "tool_call_identity_mismatch", fixture_name)
    _require(
        type(attributes.get("junjo.agent.tool.state_revision.before")) is int,
        "invalid_tool_state_revision",
        fixture_name,
    )
    requested_arguments = _validate_payload_slot(
        attributes, "junjo.agent.tool.requested_arguments", fixture_name
    )
    arguments_present = _payload_slot_present(attributes, "junjo.agent.tool.arguments")
    if arguments_present:
        _validate_payload_slot(attributes, "junjo.agent.tool.arguments", fixture_name)
    available = attributes.get("junjo.agent.tool.result_candidate.available")
    _require(type(available) is bool, "invalid_candidate_evidence", fixture_name)
    if available:
        _validate_payload_slot(
            attributes, "junjo.agent.tool.result_candidate", fixture_name
        )
        _require(
            "junjo.agent.tool.result_candidate.unavailable_reason" not in attributes,
            "invalid_candidate_evidence",
            fixture_name,
        )
    else:
        _require_payload_slot_absent(
            attributes,
            "junjo.agent.tool.result_candidate",
            "invalid_candidate_evidence",
            fixture_name,
        )
        _require(
            attributes.get("junjo.agent.tool.result_candidate.unavailable_reason")
            in {"not_invoked", "service_failed", "cancelled", "not_json_serializable"},
            "invalid_candidate_evidence",
            fixture_name,
        )
    unavailable_reason = attributes.get(
        "junjo.agent.tool.result_candidate.unavailable_reason"
    )
    _require(
        (unavailable_reason == "cancelled") == (outcome == "cancelled" and not available),
        "invalid_candidate_transport_correspondence",
        fixture_name,
    )
    started = available or unavailable_reason != "not_invoked"
    _require(
        not started or arguments_present,
        "invalid_tool_started_evidence",
        fixture_name,
    )
    if attributes.get("error.type") == "AgentToolInputValidationError":
        _require(
            not arguments_present,
            "unexpected_tool_arguments_evidence",
            fixture_name,
        )
    result_present = _payload_slot_present(attributes, "junjo.agent.tool.result")
    revision_after_present = "junjo.agent.tool.state_revision.after" in attributes
    _require(
        result_present == revision_after_present,
        "invalid_tool_result_commit_evidence",
        fixture_name,
    )
    _require(
        (outcome == "completed") == result_present,
        "invalid_tool_result_transport",
        fixture_name,
    )
    if outcome == "completed":
        _require(arguments_present, "required_tool_arguments_evidence", fixture_name)
        _require(available is True, "invalid_candidate_transport_correspondence", fixture_name)
        _require(
            type(attributes.get("junjo.agent.tool.state_revision.after")) is int,
            "invalid_tool_state_revision",
            fixture_name,
        )
    if result_present:
        _validate_payload_slot(attributes, "junjo.agent.tool.result", fixture_name)
    return {
        "id": attributes["junjo.agent.tool_call.id"],
        "ordinal": ordinal,
        "name": attributes["junjo.agent.tool.name"],
        "structuralId": attributes["junjo.agent.tool.structural_id"],
        "requestedArguments": requested_arguments,
        "requestedArgumentsMode": attributes.get(
            "junjo.agent.tool.requested_arguments.mode"
        ),
        "admitted": arguments_present,
        "started": started,
        "completed": result_present,
    }


def _validate_terminal_transport(
    span: dict[str, Any], attributes: dict[str, Any], fixture_name: str
) -> None:
    outcome = attributes.get("junjo.agent.outcome")
    status_is_error = span.get("status_code") == "2"
    error_type = attributes.get("error.type")
    exception_types = [
        event["attributes"].get("exception.type")
        for event in span.get("events_json", [])
        if isinstance(event, dict)
        and event.get("name") == "exception"
        and isinstance(event.get("attributes"), dict)
    ]
    _require(
        all(_is_portable_text(value, nonempty=True) for value in exception_types),
        "invalid_failure_evidence",
        fixture_name,
    )
    exception_matches_error = _is_portable_text(error_type, nonempty=True) and any(
        exception_type == error_type
        or (
            _is_portable_text(exception_type, nonempty=True)
            and exception_type.rsplit(".", 1)[-1] == error_type
        )
        for exception_type in exception_types
    )
    if outcome == "failed":
        _require(
            status_is_error
            and _is_portable_text(error_type, nonempty=True)
            and exception_matches_error
            and attributes.get("junjo.cancelled") is not True,
            "invalid_failure_evidence",
            fixture_name,
        )
    elif outcome == "cancelled":
        _require(
            attributes.get("junjo.cancelled") is True
            and _is_portable_text(
                attributes.get("junjo.cancelled_reason"), nonempty=True
            )
            and not status_is_error
            and "error.type" not in attributes,
            "invalid_cancellation_evidence",
            fixture_name,
        )
    else:
        _require(
            not status_is_error
            and "error.type" not in attributes
            and attributes.get("junjo.cancelled") is not True,
            "invalid_completion_evidence",
            fixture_name,
        )


def _validate_operation_transport(span: dict[str, Any], fixture_name: str) -> None:
    attributes = span["attributes_json"]
    cancelled = attributes.get("junjo.cancelled") is True
    status_is_error = span.get("status_code") == "2"
    error_type = attributes.get("error.type")
    exception_types = [
        event["attributes"].get("exception.type")
        for event in span.get("events_json", [])
        if isinstance(event, dict)
        and event.get("name") == "exception"
        and isinstance(event.get("attributes"), dict)
    ]
    _require(
        all(_is_portable_text(value, nonempty=True) for value in exception_types),
        "invalid_operation_failure_evidence",
        fixture_name,
    )
    exception_matches_error = _is_portable_text(error_type, nonempty=True) and any(
        exception_type == error_type
        or (
            _is_portable_text(exception_type, nonempty=True)
            and exception_type.rsplit(".", 1)[-1] == error_type
        )
        for exception_type in exception_types
    )
    if cancelled:
        _require(
            _is_portable_text(attributes.get("junjo.cancelled_reason"), nonempty=True)
            and not status_is_error
            and "error.type" not in attributes,
            "invalid_operation_cancellation_evidence",
            fixture_name,
        )
    elif status_is_error or "error.type" in attributes:
        _require(
            status_is_error
            and _is_portable_text(error_type, nonempty=True)
            and exception_matches_error,
            "invalid_operation_failure_evidence",
            fixture_name,
        )
    else:
        _require(
            "junjo.cancelled_reason" not in attributes,
            "invalid_operation_completion_evidence",
            fixture_name,
        )


def _validate_limit_evidence(
    attributes: dict[str, Any], fixture_name: str
) -> None:
    roots = {
        "junjo.agent.limit.exceeded",
        "junjo.agent.limit.attempted_count",
        "junjo.agent.limit.requested_batch_size",
    }
    if attributes.get("junjo.agent.termination_reason") != "limit_exceeded":
        _require(not (roots & set(attributes)), "unexpected_limit_evidence", fixture_name)
        return
    exceeded = attributes.get("junjo.agent.limit.exceeded")
    attempted = attributes.get("junjo.agent.limit.attempted_count")
    _require(
        exceeded in {"model_requests", "tool_calls"}
        and type(attempted) is int
        and attempted >= 1,
        "invalid_limit_evidence",
        fixture_name,
    )
    if exceeded == "model_requests":
        count = attributes.get("junjo.agent.model_request.count")
        limit = attributes.get("junjo.agent.limit.model_requests")
        _require(
            count == limit
            and attempted == count + 1
            and "junjo.agent.limit.requested_batch_size" not in attributes,
            "invalid_limit_evidence",
            fixture_name,
        )
    else:
        batch = attributes.get("junjo.agent.limit.requested_batch_size")
        requested = attributes.get("junjo.agent.tool_call.requested_count")
        admitted = attributes.get("junjo.agent.tool_call.admitted_count")
        limit = attributes.get("junjo.agent.limit.tool_calls")
        _require(
            type(batch) is int
            and batch >= 1
            and type(requested) is int
            and requested > limit
            and attempted == admitted + batch,
            "invalid_limit_evidence",
            fixture_name,
        )


def _validate_boundary_candidate(
    attributes: dict[str, Any], root: str, fixture_name: str
) -> None:
    available = attributes.get(f"{root}.available")
    _require(type(available) is bool, "invalid_candidate_evidence", fixture_name)
    if available:
        _validate_payload_slot(attributes, root, fixture_name)
        _require(
            f"{root}.unavailable_reason" not in attributes,
            "invalid_candidate_evidence",
            fixture_name,
        )
    else:
        _require_payload_slot_absent(
            attributes,
            root,
            "invalid_candidate_evidence",
            fixture_name,
        )
        _require(
            attributes.get(f"{root}.unavailable_reason") == "not_json_serializable",
            "invalid_candidate_evidence",
            fixture_name,
        )


def _validate_agent_store_causality(
    fixture: dict[str, Any],
    owner: dict[str, Any],
    operations: list[dict[str, Any]],
    fixture_name: str,
) -> None:
    store_id = owner["attributes_json"].get("junjo.agent.store.id")
    if not isinstance(store_id, str):
        return
    eligible_span_ids = {id(span) for span in [owner, *operations]}
    for span in fixture["spans"]:
        if id(span) in eligible_span_ids:
            continue
        _require(
            not any(
                event.get("name") == "set_state"
                and event.get("attributes", {}).get("junjo.store.id") == store_id
                for event in span["events_json"]
            ),
            "store_causal_owner_mismatch",
            fixture_name,
        )
    allowed_owner = {"admit_tool_batch", "commit_success", "set_terminal_reason"}
    allowed_operations = {
        "model_request": {"record_model_start", "record_model_response"},
        "tool": {"record_tool_started", "record_tool_result"},
    }
    for span in [owner, *operations]:
        attributes = span["attributes_json"]
        operation_type = attributes.get("junjo.agent.operation_type")
        allowed = allowed_owner if span is owner else allowed_operations.get(operation_type, set())
        events = [
            event
            for event in span["events_json"]
            if event.get("name") == "set_state"
            and event.get("attributes", {}).get("junjo.store.id") == store_id
        ]
        _require(
            all(event["attributes"].get("junjo.store.action") in allowed for event in events),
            "store_causal_owner_mismatch",
            fixture_name,
        )
        if operation_type == "model_request":
            starts = [
                event
                for event in events
                if event["attributes"].get("junjo.store.action") == "record_model_start"
            ]
            _require(
                len(starts) == 1
                and starts[0]["attributes"].get("junjo.store.revision.after")
                == attributes.get("junjo.agent.model_request.state_revision"),
                "model_state_revision_mismatch",
                fixture_name,
            )
            responses = [
                event
                for event in events
                if event["attributes"].get("junjo.store.action")
                == "record_model_response"
            ]
            response_present = _payload_slot_present(
                attributes, "junjo.agent.model.response"
            )
            _require(
                (not response_present and not responses)
                or (response_present and len(responses) == 1),
                "model_response_causality_mismatch",
                fixture_name,
            )
        elif operation_type == "tool":
            started = [
                event
                for event in events
                if event["attributes"].get("junjo.store.action") == "record_tool_started"
            ]
            results = [
                event
                for event in events
                if event["attributes"].get("junjo.store.action") == "record_tool_result"
            ]
            before = attributes.get("junjo.agent.tool.state_revision.before")
            after = attributes.get("junjo.agent.tool.state_revision.after")
            started_expected = (
                attributes.get("junjo.agent.tool.result_candidate.available") is True
                or attributes.get(
                    "junjo.agent.tool.result_candidate.unavailable_reason"
                )
                != "not_invoked"
            )
            _require(
                (not started_expected and not started)
                or (
                    started_expected
                    and len(started) == 1
                    and started[0]["attributes"].get("junjo.store.revision.before") == before
                ),
                "tool_state_revision_mismatch",
                fixture_name,
            )
            _require(
                (after is None and not results)
                or (
                    after is not None
                    and len(results) == 1
                    and results[0]["attributes"].get("junjo.store.revision.after") == after
                ),
                "tool_state_revision_mismatch",
                fixture_name,
            )


def _validate_executable_parentage(
    fixture: dict[str, Any],
    owner: dict[str, Any],
    operations: list[dict[str, Any]],
    fixture_name: str,
) -> None:
    owner_attributes = owner["attributes_json"]
    parent_span_id = owner.get("parent_span_id")
    parent_keys = (
        "junjo.parent_executable_definition_id",
        "junjo.parent_executable_runtime_id",
        "junjo.parent_executable_structural_id",
    )
    parent_type_key = "junjo.parent_executable_type"
    if parent_span_id is None:
        _require(
            parent_type_key not in owner_attributes
            and not any(key in owner_attributes for key in parent_keys),
            "parent_executable_correspondence_mismatch",
            fixture_name,
        )
    else:
        declared = tuple(owner_attributes.get(key) for key in parent_keys)
        declared_type = owner_attributes.get(parent_type_key)
        physical_matches = [
            span
            for span in fixture["spans"]
            if span.get("span_id") == parent_span_id
        ]
        declared_present = declared_type is not None or any(
            value is not None for value in declared
        )
        if not declared_present:
            if len(physical_matches) == 1:
                physical_attributes = physical_matches[0]["attributes_json"]
                _require(
                    physical_attributes.get("junjo.span_type")
                    not in {"workflow", "subflow", "node", "run_concurrent", "agent"}
                    and "junjo.agent.operation_type" not in physical_attributes,
                    "parent_executable_correspondence_mismatch",
                    fixture_name,
                )
        else:
            _require(
                len(physical_matches) == 1,
                "parent_executable_missing",
                fixture_name,
            )
            _require(
                declared_type
                in {"workflow", "subflow", "node", "run_concurrent", "agent"}
                and all(_is_portable_text(value, nonempty=True) for value in declared),
                "parent_executable_correspondence_mismatch",
                fixture_name,
            )
            semantic_matches = [
                span
                for span in fixture["spans"]
                if span["attributes_json"].get("junjo.span_type")
                == declared_type
                and tuple(
                    span["attributes_json"].get(key)
                    for key in (
                        "junjo.executable_definition_id",
                        "junjo.executable_runtime_id",
                        "junjo.executable_structural_id",
                    )
                )
                == declared
            ]
            _require(
                len(semantic_matches) == 1,
                "parent_executable_correspondence_mismatch",
                fixture_name,
            )

    tool_span_ids = {
        span["span_id"]
        for span in operations
        if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
    }
    expected_parent = (
        "agent",
        owner_attributes.get("junjo.executable_definition_id"),
        owner_attributes.get("junjo.executable_runtime_id"),
        owner_attributes.get("junjo.executable_structural_id"),
    )
    for span in fixture["spans"]:
        attributes = span["attributes_json"]
        if (
            attributes.get("junjo.span_type") in {"workflow", "agent"}
            and span.get("parent_span_id") in tool_span_ids
        ):
            identity_values = [
                attributes.get("junjo.executable_definition_id"),
                attributes.get("junjo.executable_runtime_id"),
                attributes.get("junjo.executable_structural_id"),
                (
                    attributes.get("junjo.agent.name")
                    if attributes.get("junjo.span_type") == "agent"
                    else span.get("name")
                ),
            ]
            _require(
                all(_is_portable_text(value, nonempty=True) for value in identity_values),
                "invalid_nested_executable",
                fixture_name,
            )
            declared = (
                attributes.get(parent_type_key),
                *(attributes.get(key) for key in parent_keys),
            )
            _require(
                declared == expected_parent,
                "nested_parent_correspondence_mismatch",
                fixture_name,
            )


def _validate_agent_semantic_attribute_scalars(
    fixture: dict[str, Any], fixture_name: str
) -> None:
    """Enforce OTLP scalar storage for every Junjo-owned semantic attribute."""
    for span_index, span in enumerate(fixture["spans"]):
        scopes = [("attributes", span["attributes_json"])]
        scopes.extend(
            (f"events[{event_index}].attributes", event["attributes"])
            for event_index, event in enumerate(span["events_json"])
        )
        for scope, attributes in scopes:
            for key, value in attributes.items():
                owned = (
                    key.startswith("junjo.")
                    or key == "error.type"
                    or key.startswith("exception.")
                )
                if owned:
                    _require(
                        value is None
                        or isinstance(value, (str, bool, int, float)),
                        "invalid_semantic_attribute_scalar",
                        f"{fixture_name}: spans[{span_index}].{scope}.{key}",
                    )


def _validate_agent_fixture(fixture: dict[str, Any], fixture_name: str) -> None:
    _validate_agent_semantic_attribute_scalars(fixture, fixture_name)
    owners = [
        span for span in fixture["spans"] if span["attributes_json"].get("junjo.span_type") == "agent"
    ]
    _require(bool(owners), "missing_agent_span", fixture_name)
    for owner in owners:
        attributes = owner["attributes_json"]
        for key in (
            "junjo.executable_definition_id",
            "junjo.executable_runtime_id",
            "junjo.executable_structural_id",
            "junjo.agent.key",
            "junjo.agent.name",
            "junjo.agent.runtime_id",
        ):
            _require(
                _is_portable_text(attributes.get(key), nonempty=True),
                "missing_agent_identity",
                fixture_name,
            )
        _require(
            attributes["junjo.agent.runtime_id"] == attributes["junjo.executable_runtime_id"],
            "agent_runtime_mismatch",
            fixture_name,
        )
        _require(
            re.fullmatch(
                r"agent_sha256:[0-9a-f]{64}",
                attributes["junjo.executable_structural_id"],
            )
            is not None,
            "invalid_agent_structural_id",
            fixture_name,
        )
        definition_value = _validate_payload_slot(
            attributes, "junjo.agent.definition_snapshot", fixture_name
        )
        state_available = attributes.get("junjo.agent.state.available")
        _require(type(state_available) is bool, "invalid_state_availability", fixture_name)
        input_value = None
        store_states = None
        if state_available:
            input_value = _validate_payload_slot(
                attributes, "junjo.agent.input", fixture_name
            )
            store_states = _validate_agent_store(fixture, attributes, fixture_name)
        else:
            _require_payload_slot_absent(
                attributes,
                "junjo.agent.input",
                "unexpected_boundary_input_evidence",
                fixture_name,
            )
            forbidden_store_facts = any(
                key == "junjo.agent.store.id"
                or key.startswith("junjo.agent.state.start")
                or key.startswith("junjo.agent.state.end")
                or key.startswith("junjo.store.")
                for key in attributes
            )
            owner_store_events = any(
                isinstance(event, dict) and event.get("name") == "set_state"
                for event in owner.get("events_json", [])
            )
            _require(
                not forbidden_store_facts and not owner_store_events,
                "fabricated_boundary_store",
                fixture_name,
            )

        limits = {
            "model": attributes.get("junjo.agent.limit.model_requests"),
            "tool": attributes.get("junjo.agent.limit.tool_calls"),
        }
        _require(
            all(type(value) is int and value >= 1 for value in limits.values()),
            "invalid_agent_limit",
            fixture_name,
        )
        count_keys = (
            "junjo.agent.operation.count",
            "junjo.agent.model_request.count",
            "junjo.agent.tool_call.requested_count",
            "junjo.agent.tool_call.admitted_count",
            "junjo.agent.tool_call.started_count",
            "junjo.agent.tool_call.completed_count",
        )
        for key in count_keys:
            _require(type(attributes.get(key)) is int and attributes[key] >= 0, "invalid_agent_count", fixture_name)
        completed = attributes["junjo.agent.tool_call.completed_count"]
        started = attributes["junjo.agent.tool_call.started_count"]
        admitted = attributes["junjo.agent.tool_call.admitted_count"]
        requested = attributes["junjo.agent.tool_call.requested_count"]
        _require(completed <= started <= admitted <= requested, "tool_count_inequality", fixture_name)
        _require(
            admitted <= limits["tool"],
            "tool_limit_mismatch",
            fixture_name,
        )
        _require(
            attributes["junjo.agent.model_request.count"] <= limits["model"],
            "model_limit_mismatch",
            fixture_name,
        )
        definition = _validate_definition_snapshot(
            definition_value, attributes, fixture_name
        )

        runtime_id = attributes["junjo.agent.runtime_id"]
        operations = [
            span
            for span in fixture["spans"]
            if span["attributes_json"].get("junjo.agent.runtime_id") == runtime_id
            and "junjo.agent.operation_type" in span["attributes_json"]
        ]
        _require(
            all(
                span["attributes_json"].get("junjo.agent.key")
                == attributes["junjo.agent.key"]
                and span.get("parent_span_id") == owner.get("span_id")
                for span in operations
            ),
            "operation_owner_mismatch",
            fixture_name,
        )
        operation_count = attributes["junjo.agent.operation.count"]
        sequences = [
            span["attributes_json"].get("junjo.agent.operation.sequence") for span in operations
        ]
        _validate_contiguous_sequence(sequences, operation_count, "operation", fixture_name)
        model_operations = [
            span
            for span in operations
            if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
        ]
        tool_operations = [
            span
            for span in operations
            if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
        ]
        _require(
            len(model_operations) + len(tool_operations) == len(operations),
            "invalid_operation_type",
            fixture_name,
        )
        for operation in operations:
            _validate_operation_transport(operation, fixture_name)
        _validate_executable_parentage(fixture, owner, operations, fixture_name)
        _require(
            len(model_operations) == attributes["junjo.agent.model_request.count"],
            "model_count_mismatch",
            fixture_name,
        )
        model_ordinals = [
            span["attributes_json"].get("junjo.agent.model_request.ordinal")
            for span in model_operations
        ]
        _require(
            sorted(model_ordinals) == list(range(1, len(model_operations) + 1)),
            "model_ordinal_noncontiguous",
            fixture_name,
        )
        requested_calls: list[dict[str, Any]] = []
        response_usage_evidence: list[dict[str, Any] | None] = []
        opaque_tool_call_response = False
        final_output_response_count = 0
        for span in model_operations:
            operation_attributes = span["attributes_json"]
            calls, response_usage, response_occurred, response = _validate_model_operation(
                span, fixture_name, definition
            )
            requested_calls.extend(calls)
            if response_occurred:
                response_usage_evidence.append(response_usage)
            if response is None and operation_attributes.get(
                "junjo.agent.model.response_type"
            ) == "tool_calls":
                opaque_tool_call_response = True
            if operation_attributes.get("junjo.agent.model.response_type") == "final_output":
                final_output_response_count += 1
        if not opaque_tool_call_response:
            _require(len(requested_calls) == requested, "requested_tool_count_mismatch", fixture_name)
        requested_identities: list[tuple[str, int]] = []
        for ordinal, call in enumerate(requested_calls, start=1):
            _require(isinstance(call, dict), "invalid_model_response", fixture_name)
            call_id = call.get("id")
            _require(isinstance(call_id, str) and call_id, "tool_call_identity_mismatch", fixture_name)
            requested_identities.append((call_id, ordinal))
        _require(
            len({call_id for call_id, _ in requested_identities}) == len(requested_identities),
            "tool_call_identity_duplicate",
            fixture_name,
        )
        tool_evidence: list[dict[str, Any]] = []
        for span in tool_operations:
            tool_attributes = span["attributes_json"]
            evidence = _validate_tool_operation(span, fixture_name)
            tool_evidence.append(evidence)
            identity = (
                tool_attributes["junjo.agent.tool_call.id"],
                tool_attributes["junjo.agent.tool_call.ordinal"],
            )
            if not opaque_tool_call_response:
                _require(identity in requested_identities, "tool_call_identity_mismatch", fixture_name)
        tool_identities = [(tool["id"], tool["ordinal"]) for tool in tool_evidence]
        _require(
            len(tool_identities) == len(set(tool_identities)),
            "tool_call_identity_duplicate",
            fixture_name,
        )
        calls_by_identity = {
            (call["id"], ordinal): call
            for ordinal, call in enumerate(requested_calls, start=1)
        }
        for tool in tool_evidence:
            if not opaque_tool_call_response:
                call = calls_by_identity[(tool["id"], tool["ordinal"])]
                _require(
                    tool["name"] == call["name"]
                    and (
                        tool["requestedArgumentsMode"] != "full"
                        or tool["requestedArguments"] == call["arguments"]
                    ),
                    "tool_operation_correspondence_mismatch",
                    fixture_name,
                )
            if definition is not None:
                declared_tool = definition["toolByName"].get(tool["name"])
                _require(
                    declared_tool is not None
                    and tool["structuralId"] == declared_tool["structuralId"],
                    "tool_operation_correspondence_mismatch",
                    fixture_name,
                )
        admitted_ids: set[str] | None = None
        if (
            store_states is not None
            and attributes.get("junjo.agent.state.end.mode") == "full"
            and isinstance(store_states[1], dict)
        ):
            raw_admitted_ids = store_states[1].get("admitted_tool_call_ids")
            _require(
                isinstance(raw_admitted_ids, list)
                and all(
                    isinstance(call_id, str) and call_id
                    for call_id in raw_admitted_ids
                )
                and len(raw_admitted_ids) == len(set(raw_admitted_ids)),
                "invalid_admission_evidence",
                fixture_name,
            )
            admitted_ids = set(raw_admitted_ids)
            if not opaque_tool_call_response:
                _require(
                    admitted_ids <= {call["id"] for call in requested_calls},
                    "invalid_admission_evidence",
                    fixture_name,
                )
        expected_tool_counts = {
            "admitted": len(admitted_ids) if admitted_ids is not None else admitted,
            "started": sum(tool["started"] for tool in tool_evidence),
            "completed": sum(tool["completed"] for tool in tool_evidence),
        }
        _require(
            expected_tool_counts
            == {"admitted": admitted, "started": started, "completed": completed},
            "tool_count_reconciliation_mismatch",
            fixture_name,
        )
        if admitted_ids is not None:
            _require(
                all(
                    tool["admitted"] == (tool["id"] in admitted_ids)
                    for tool in tool_evidence
                ),
                "invalid_tool_argument_admission",
                fixture_name,
            )

        _validate_agent_store_causality(fixture, owner, operations, fixture_name)

        aggregate_usage = _validate_usage_attribute(
            attributes,
            "junjo.agent.usage",
            "agent-usage.v1.schema.json",
            "invalid_agent_usage",
            fixture_name,
        )
        expected_usage: dict[str, Any] = {
            "v": 1,
            "modelResponses": len(response_usage_evidence),
            "fields": {},
        }
        for usage in response_usage_evidence:
            if usage is None:
                continue
            for field, value in usage.items():
                if field == "v":
                    continue
                aggregate = expected_usage["fields"].setdefault(
                    field, {"sum": 0, "observations": 0}
                )
                aggregate["sum"] += value
                aggregate["observations"] += 1
        _require(aggregate_usage == expected_usage, "agent_usage_mismatch", fixture_name)

        outcome = attributes.get("junjo.agent.outcome")
        reason = attributes.get("junjo.agent.termination_reason")
        _require(outcome in {"completed", "failed", "cancelled"}, "invalid_agent_outcome", fixture_name)
        _require(
            reason
            in {
                "final_output",
                "input_validation_error",
                "history_validation_error",
                "limit_exceeded",
                "model_error",
                "model_response_error",
                "unknown_tool",
                "tool_input_validation_error",
                "tool_error",
                "tool_output_validation_error",
                "output_validation_error",
                "cancelled",
                "internal_error",
            },
            "invalid_termination_reason",
            fixture_name,
        )
        _validate_terminal_transport(owner, attributes, fixture_name)
        _validate_limit_evidence(attributes, fixture_name)
        expected_outcome = (
            "completed"
            if reason == "final_output"
            else "cancelled"
            if reason == "cancelled"
            else "failed"
        )
        _require(
            outcome == expected_outcome,
            "terminal_outcome_reason_mismatch",
            fixture_name,
        )
        boundary_candidates = {
            "input_validation_error": "junjo.agent.input_candidate",
            "history_validation_error": "junjo.agent.history_candidate",
        }
        expected_candidate = boundary_candidates.get(reason)
        for candidate_root in boundary_candidates.values():
            if candidate_root == expected_candidate:
                _validate_boundary_candidate(attributes, candidate_root, fixture_name)
            else:
                _require(
                    not _candidate_present(attributes, candidate_root),
                    "unexpected_boundary_candidate_evidence",
                    fixture_name,
                )
        if state_available is False:
            _require(
                reason in boundary_candidates
                or (
                    reason == "internal_error"
                    and attributes.get("error.type") == "AgentAdmissionError"
                ),
                "invalid_unavailable_agent_state",
                fixture_name,
            )
            _require(
                all(attributes[key] == 0 for key in count_keys)
                and aggregate_usage == {"v": 1, "modelResponses": 0, "fields": {}},
                "invalid_unavailable_agent_activity",
                fixture_name,
            )
        requires_unavailable_state = reason in boundary_candidates or (
            reason == "internal_error"
            and attributes.get("error.type") == "AgentAdmissionError"
        )
        _require(
            not requires_unavailable_state or state_available is False,
            "invalid_unavailable_agent_state",
            fixture_name,
        )
        _require(
            requested <= limits["tool"]
            or (
                reason == "limit_exceeded"
                and attributes.get("junjo.agent.limit.exceeded") == "tool_calls"
            ),
            "invalid_limit_evidence",
            fixture_name,
        )
        output_value = None
        if outcome == "completed":
            output_value = _validate_payload_slot(
                attributes, "junjo.agent.output", fixture_name
            )
        else:
            _require_payload_slot_absent(
                attributes,
                "junjo.agent.output",
                "unexpected_output_evidence",
                fixture_name,
            )
        if store_states is not None:
            start_state, end_state = store_states
            if (
                attributes.get("junjo.agent.state.start.mode") == "full"
                and attributes.get("junjo.agent.input.mode") == "full"
            ):
                _require(
                    isinstance(start_state, dict)
                    and start_state.get("input") == input_value,
                    "state_owner_mismatch",
                    fixture_name,
                )
            if attributes.get("junjo.agent.state.end.mode") == "full":
                expected_state = {
                    "model_request_count": attributes["junjo.agent.model_request.count"],
                    "tool_call_requested_count": requested,
                    "tool_call_admitted_count": admitted,
                    "tool_call_started_count": started,
                    "tool_call_completed_count": completed,
                    "usage": aggregate_usage,
                }
                _require(
                    isinstance(end_state, dict)
                    and all(end_state.get(key) == value for key, value in expected_state.items()),
                    "state_owner_mismatch",
                    fixture_name,
                )
                _require(
                    end_state.get("terminal_reason") == reason,
                    "state_owner_mismatch",
                    fixture_name,
                )
                if outcome == "completed":
                    _require(
                        end_state.get("final_output_available") is True
                        and end_state.get("final_output") == output_value,
                        "final_output_mismatch",
                        fixture_name,
                    )
                else:
                    _require(
                        end_state.get("final_output_available") is False
                        and end_state.get("final_output") is None,
                        "final_output_mismatch",
                        fixture_name,
                    )
        if outcome == "completed":
            _require(
                final_output_response_count == 1,
                "final_output_mismatch",
                fixture_name,
            )


def _validate_schema_versions(contract_version: int) -> int:
    schema_paths = sorted(SCHEMA_ROOT.glob("*.json"))
    schemas = {path.name: _load_json(path) for path in schema_paths}
    SCHEMAS.clear()
    SCHEMAS.update(schemas)
    for name, schema in schemas.items():
        _audit_schema_definition(schema, name)
    _validate_schema_evaluator_guard()
    fixture_version = schemas["telemetry-fixture.schema.json"]["properties"]["contract_version"]["const"]
    _require(fixture_version == contract_version, "schema_version_mismatch", "telemetry fixture")
    graph_version = schemas["execution-graph-snapshot.v2.schema.json"]["properties"]["v"]["const"]
    _require(graph_version == 2, "schema_version_mismatch", "execution graph")
    nested_tool = schemas["agent-structural-material.v1.schema.json"]["properties"]["tools"][
        "items"
    ]
    _require(
        "v" not in nested_tool["required"] and "v" not in nested_tool["properties"],
        "structural_schema_mismatch",
        "nested Agent Tool material must omit v",
    )
    standalone_tool = schemas["tool-structural-material.v1.schema.json"]
    _require(
        "v" in standalone_tool["required"] and standalone_tool["properties"]["v"]["const"] == 1,
        "structural_schema_mismatch",
        "standalone Tool material requires v=1",
    )
    return len(schema_paths)


def _validate_fingerprints() -> int:
    path = FIXTURE_ROOT / "fingerprints" / "agent-structural-v1.json"
    fixture = _load_json(path)
    _require(fixture.get("v") == 1, "fingerprint_version_mismatch", path.name)
    vectors = fixture.get("vectors")
    _require(isinstance(vectors, list) and vectors, "missing_fingerprint_vectors", path.name)
    names: set[str] = set()
    for vector in vectors:
        _require(isinstance(vector, dict), "invalid_fingerprint_vector", path.name)
        name = vector.get("name")
        _require(isinstance(name, str) and name not in names, "invalid_fingerprint_vector", path.name)
        names.add(name)
        kind = vector.get("kind")
        _require(kind in {"agent", "tool"}, "invalid_fingerprint_vector", str(name))
        canonical = vector.get("canonical")
        _require(isinstance(canonical, str), "invalid_fingerprint_vector", str(name))
        _require(
            _decode_json(
                canonical,
                "fingerprint_material_mismatch",
                str(name),
                enforce_portable=True,
            )
            == vector.get("material"),
            "fingerprint_material_mismatch",
            str(name),
        )
        try:
            recomputed = canonical_json_dumps(vector.get("material"))
        except CanonicalizationError as error:
            raise ContractValidationError(
                "fingerprint_material_not_ijson", f"{name}: {error}"
            ) from error
        _require(
            canonical.encode("utf-8") == recomputed,
            "fingerprint_canonical_mismatch",
            str(name),
        )
        expected = f"{kind}_sha256:{hashlib.sha256(recomputed).hexdigest()}"
        _require(vector.get("structural_id") == expected, "fingerprint_hash_mismatch", str(name))
        if kind == "agent":
            tools = vector["material"].get("tools")
            _require(isinstance(tools, list), "fingerprint_material_mismatch", str(name))
            _require(
                all(isinstance(tool, dict) and "v" not in tool for tool in tools),
                "fingerprint_material_mismatch",
                f"{name}: nested Tool v",
            )
    required_names = {
        "plain",
        "safe_integer_boundaries",
        "negative_zero",
        "exponent",
        "unicode_composed",
        "unicode_decomposed",
        "tool_plain",
        "agent_normalized_schema_profile",
        "tool_normalized_schema_profile",
    }
    _require(required_names <= names, "missing_fingerprint_vectors", path.name)
    by_name = {vector["name"]: vector for vector in vectors}
    _require(
        by_name["tool_normalized_schema_profile"]["structural_id"]
        == "tool_sha256:76f33bc1c63144439629046181f84cce99d8cb8933285cb7dbaa821f908afa4b",
        "fingerprint_hash_mismatch",
        "tool_normalized_schema_profile",
    )
    for invalid in (
        {"unsafe": 9007199254740992},
        {"number": float("nan")},
        {"number": float("inf")},
        {"surrogate": "\ud800"},
        {1: "non-string-key"},
    ):
        try:
            canonical_json_dumps(invalid)
        except CanonicalizationError:
            continue
        raise ContractValidationError(
            "fingerprint_invalid_ijson_accepted", repr(invalid)
        )
    return len(vectors) + _validate_schema_normalization_vectors()


def _validate_schema_normalization_vectors() -> int:
    path = FIXTURE_ROOT / "fingerprints" / "schema-normalization-v1.json"
    fixture = _load_json(path)
    _require(fixture.get("v") == 1, "fingerprint_version_mismatch", path.name)
    _require(
        fixture.get("profile") == "junjo.generated-json-schema.v1",
        "schema_profile_mismatch",
        path.name,
    )
    vectors = fixture.get("vectors")
    invalid = fixture.get("invalid")
    _require(isinstance(vectors, list) and vectors, "missing_schema_vectors", path.name)
    _require(isinstance(invalid, list) and invalid, "missing_schema_vectors", path.name)

    required_names = {
        "renamed_nested_definitions",
        "recursive_definitions",
        "discriminator_mapping",
        "application_property_named_title",
        "object_insertion_and_set_order",
        "open_dictionary_schema",
    }
    names: set[str] = set()
    normalized_by_name: dict[str, dict[str, Any]] = {}
    for vector in vectors:
        _require(isinstance(vector, dict), "invalid_schema_vector", path.name)
        name = vector.get("name")
        inputs = vector.get("inputs")
        expected = vector.get("normalized")
        _require(
            isinstance(name, str) and name not in names,
            "invalid_schema_vector",
            path.name,
        )
        _require(
            isinstance(inputs, list)
            and len(inputs) >= 2
            and all(isinstance(value, dict) for value in inputs),
            "invalid_schema_vector",
            str(name),
        )
        _require(isinstance(expected, dict), "invalid_schema_vector", str(name))
        names.add(name)
        normalized_by_name[name] = expected
        for schema in inputs:
            try:
                actual = normalize_generated_schema(schema)
            except SchemaNormalizationError as error:
                raise ContractValidationError(
                    "schema_normalization_failed", f"{name}: {error}"
                ) from error
            _require(actual == expected, "schema_normalization_mismatch", str(name))
        _require(
            normalize_generated_schema(expected) == expected,
            "schema_normalization_not_idempotent",
            str(name),
        )
    _require(required_names <= names, "missing_schema_vectors", path.name)

    nested = normalized_by_name["renamed_nested_definitions"]
    _require(
        set(nested.get("$defs", {})) == {"d0", "d1"},
        "schema_normalization_mismatch",
        "reachable definition renaming",
    )
    recursive = normalized_by_name["recursive_definitions"]
    _require(
        recursive.get("$defs", {})
        .get("d0", {})
        .get("properties", {})
        .get("children", {})
        .get("items", {})
        .get("$ref")
        == "#/$defs/d0",
        "schema_normalization_mismatch",
        "recursive definition",
    )
    discriminator = normalized_by_name["discriminator_mapping"]
    pet = discriminator.get("properties", {}).get("pet", {})
    _require(
        pet.get("discriminator", {}).get("mapping")
        == {"cat": "#/$defs/d0", "dog": "#/$defs/d1"},
        "schema_normalization_mismatch",
        "discriminator mapping",
    )
    title = normalized_by_name["application_property_named_title"]
    _require(
        "title" not in title
        and title.get("properties", {}).get("title") == {"type": "string"},
        "schema_normalization_mismatch",
        "application property named title",
    )
    ordered = normalized_by_name["object_insertion_and_set_order"]
    _require(
        ordered.get("required") == ["first", "second"]
        and ordered.get("properties", {}).get("first", {}).get("type")
        == ["null", "string"]
        and ordered.get("properties", {}).get("second", {}).get("enum")
        == ["alpha", "beta"]
        and ordered.get("dependentRequired", {}).get("second")
        == ["first", "third"]
        and ordered.get("examples")
        == [{"second": "beta"}, {"second": "alpha"}]
        and ordered.get("oneOf")
        == [{"required": ["first"]}, {"required": ["second"]}],
        "schema_normalization_mismatch",
        "set-valued versus ordered arrays",
    )

    invalid_names: set[str] = set()
    for vector in invalid:
        _require(isinstance(vector, dict), "invalid_schema_vector", path.name)
        name = vector.get("name")
        schema = vector.get("input")
        expected_error = vector.get("expected_error")
        _require(
            isinstance(name, str)
            and name not in invalid_names
            and isinstance(schema, dict)
            and isinstance(expected_error, str),
            "invalid_schema_vector",
            path.name,
        )
        invalid_names.add(name)
        try:
            normalize_generated_schema(schema)
        except SchemaNormalizationError as error:
            _require(
                error.code == expected_error,
                "schema_normalization_error_mismatch",
                name,
            )
        else:
            raise ContractValidationError("invalid_schema_vector_accepted", name)
    _require(
        invalid_names
        == {
            "duplicate_required_member",
            "duplicate_type_member",
            "duplicate_enum_member",
            "duplicate_dependent_required_member",
            "null_additional_properties",
            "numeric_additional_properties",
            "open_structured_object",
        },
        "missing_schema_vectors",
        "schema-profile rejection vectors",
    )
    return len(vectors) + len(invalid)


def _validate_patch_vectors() -> int:
    path = FIXTURE_ROOT / "store" / "rfc6902-replay.json"
    fixture = _load_json(path)
    _require(fixture.get("v") == 1, "patch_vector_version_mismatch", path.name)
    valid = fixture.get("valid")
    invalid = fixture.get("invalid")
    _require(isinstance(valid, list) and valid, "missing_patch_vectors", path.name)
    _require(isinstance(invalid, list) and invalid, "missing_patch_vectors", path.name)
    for vector in valid:
        observed = _apply_patch(vector["start"], vector["patch"], vector["name"])
        _require(observed == vector["end"], "patch_replay_mismatch", vector["name"])
    for vector in invalid:
        try:
            _apply_patch(vector["start"], vector["patch"], vector["name"])
        except ContractValidationError as error:
            _require(
                error.code == vector["expected_diagnostic"],
                "unexpected_diagnostic",
                vector["name"],
            )
        else:
            raise ContractValidationError("invalid_patch_vector_accepted", vector["name"])
    return len(valid) + len(invalid)


def _validate_bounded_malformed_agent_scalars(
    producer_root: Path,
    contract_version: int,
) -> int:
    """Prove malformed semantic attribute containers fail with typed diagnostics."""
    contexts = (
        "direct_typed_completion",
        "malformed_tool_arguments",
        "boundary_input_history_rejection",
        "tool_invokes_nested_workflow",
    )
    checked = 0
    for context in contexts:
        original = _load_json(producer_root / f"{context}.json")
        roles: dict[str, tuple[int, int | None]] = {}
        for span_index, span in enumerate(original["spans"]):
            for key in span["attributes_json"]:
                if key.startswith("junjo.") or key == "error.type":
                    roles.setdefault(key, (span_index, None))
            for event_index, event in enumerate(span["events_json"]):
                for key in event["attributes"]:
                    if key.startswith("junjo.") or key.startswith("exception."):
                        roles.setdefault(key, (span_index, event_index))
        for key, (span_index, event_index) in roles.items():
            for malformed in ({}, []):
                fixture = copy.deepcopy(original)
                target = fixture["spans"][span_index]
                attributes = (
                    target["attributes_json"]
                    if event_index is None
                    else target["events_json"][event_index]["attributes"]
                )
                attributes[key] = malformed
                try:
                    _validate_common_fixture(fixture, context, contract_version)
                    _validate_agent_fixture(fixture, context)
                except ContractValidationError:
                    checked += 1
                else:
                    raise ContractValidationError(
                        "malformed_semantic_attribute_accepted",
                        f"{context}: {key} accepted {type(malformed).__name__}",
                    )
    for malformed_root in (None, [], "fixture", 1):
        try:
            _validate_common_fixture(malformed_root, "fixture", contract_version)
        except ContractValidationError:
            checked += 1
        else:
            raise ContractValidationError(
                "malformed_fixture_root_accepted",
                type(malformed_root).__name__,
            )
    correlated = _load_json(producer_root / "tool_invokes_nested_workflow.json")
    owner = next(
        span
        for span in correlated["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    owner["attributes_json"].pop("junjo.correlation.id")
    try:
        _validate_common_fixture(
            correlated,
            "tool_invokes_nested_workflow",
            contract_version,
        )
    except ContractValidationError as error:
        _require(
            error.code == "incomplete_execution_correlation",
            "unexpected_diagnostic",
            "incomplete execution correlation",
        )
        checked += 1
    else:
        raise ContractValidationError(
            "incomplete_execution_correlation_accepted",
            "tool_invokes_nested_workflow",
        )
    return checked


def main() -> None:
    contract_version = int((CONTRACT_ROOT / "VERSION").read_text(encoding="utf-8").strip())
    _require(contract_version == 2, "wrong_contract_version", "active VERSION must be 2")
    schema_count = _validate_schema_versions(contract_version)

    workflow_paths = sorted((FIXTURE_ROOT / "workflow").glob("*.json"))
    _require(
        {path.stem for path in workflow_paths} == WORKFLOW_SCENARIOS,
        "incomplete_scenario_set",
        "Workflow fixtures",
    )
    for path in workflow_paths:
        fixture = _load_json(path)
        _validate_common_fixture(fixture, path.stem, contract_version)
        _validate_workflow_fixture(fixture, path.stem)

    producer_root = FIXTURE_ROOT / "agent" / "producer"
    consumer_root = FIXTURE_ROOT / "agent" / "consumer"
    producer_paths = sorted(producer_root.glob("*.json"))
    consumer_paths = sorted(consumer_root.glob("*.json"))
    from generate_v2_fixtures import AGENT_CONSUMER_SCENARIOS, AGENT_PRODUCER_SCENARIOS

    _require(
        {path.stem for path in producer_paths} == set(AGENT_PRODUCER_SCENARIOS),
        "incomplete_scenario_set",
        "Agent producer fixtures",
    )
    _require(
        {path.stem for path in consumer_paths} == set(AGENT_CONSUMER_SCENARIOS),
        "incomplete_scenario_set",
        "Agent consumer fixtures",
    )
    for path in [*producer_paths, *consumer_paths]:
        fixture = _load_json(path)
        _validate_common_fixture(fixture, path.stem, contract_version)
        _validate_agent_fixture(fixture, path.stem)

    malformed_scalar_count = _validate_bounded_malformed_agent_scalars(
        producer_root,
        contract_version,
    )

    invalid_paths = sorted((FIXTURE_ROOT / "invalid" / "agent").glob("*.json"))
    _require(bool(invalid_paths), "incomplete_scenario_set", "invalid Agent fixtures")
    for path in invalid_paths:
        derivative = _load_json(path)
        expected = derivative.get("expected_diagnostic")
        fixture = derivative.get("fixture")
        _require(isinstance(expected, str) and expected, "missing_expected_diagnostic", path.stem)
        _require(isinstance(fixture, dict), "invalid_fixture_wrapper", path.stem)
        try:
            _validate_common_fixture(fixture, path.stem, contract_version)
            _validate_agent_fixture(fixture, path.stem)
        except ContractValidationError as error:
            _require(
                error.code == expected,
                "unexpected_diagnostic",
                f"{path.stem}: expected {expected}, observed {error.code}",
            )
        else:
            raise ContractValidationError(
                "invalid_fixture_accepted", f"{path.stem}: expected {expected}"
            )

    fingerprint_count = _validate_fingerprints()
    patch_vector_count = _validate_patch_vectors()

    print(
        f"Telemetry contract {contract_version}: validated {schema_count} schemas and "
        f"{len(workflow_paths)} Workflow, {len(producer_paths)} Agent producer, "
        f"{len(consumer_paths)} Agent consumer, {len(invalid_paths)} invalid, and "
        f"{fingerprint_count} fingerprint plus {patch_vector_count} RFC 6902 vectors; "
        f"rejected {malformed_scalar_count} bounded malformed scalar mutations."
    )


if __name__ == "__main__":
    main()
