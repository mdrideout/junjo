"""Deterministic language-neutral JSON Schema normalization for Agent contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

import rfc8785
from pydantic import TypeAdapter

from .._json import (
    FrozenJsonValue,
    JsonBoundaryError,
    freeze_json,
    normalize_json,
    thaw_json,
)

_SCHEMA_MAP_KEYWORDS = frozenset({"$defs", "definitions", "dependentSchemas", "patternProperties", "properties"})
_SCHEMA_ARRAY_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
_SCHEMA_SINGLE_KEYWORDS = frozenset(
    {
        "additionalItems",
        "additionalProperties",
        "contains",
        "contentSchema",
        "else",
        "if",
        "items",
        "not",
        "propertyNames",
        "then",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
)
_SCHEMA_KEYWORD_UNHANDLED = object()


def schema_for(adapter: TypeAdapter) -> Mapping[str, FrozenJsonValue]:
    """Generate one deterministic schema under Junjo's language-neutral profile."""

    _require_lossless_core_schema(adapter.core_schema)
    validation_schema = normalize_schema(adapter.json_schema(mode="validation"))
    serialization_schema = normalize_schema(adapter.json_schema(mode="serialization"))
    if validation_schema != serialization_schema:
        raise JsonBoundaryError("Boundary validation and serialization schemas must be identical after normalization.")
    schema = validation_schema
    frozen = freeze_json(schema)
    if not isinstance(frozen, Mapping):
        raise JsonBoundaryError("Generated JSON Schema must be an object.")
    return cast(Mapping[str, FrozenJsonValue], frozen)


def normalize_schema(schema: Mapping[str, object]) -> dict[str, object]:
    """Normalize one schema without changing ordered applicator semantics."""

    # Guard arbitrary schema-shaped input before the recursive normalizer runs.
    # The shared transport limit is deliberately checked on the unmodified
    # document so excessive input cannot surface as ``RecursionError``.
    portable_schema = thaw_json(freeze_json(schema))
    without_titles = _normalize_schema_node(portable_schema)
    if not isinstance(without_titles, dict):
        raise JsonBoundaryError("Generated JSON Schema must be an object.")
    return _LocalDefinitionNormalizer(cast(dict[str, object], without_titles)).normalize()


def schema_proves_object_root(schema: Mapping[str, object]) -> bool:
    """Return whether every value accepted by ``schema`` must be an object."""

    definitions_value = schema.get("$defs", {})
    definitions = (
        _string_mapping(definitions_value, "JSON Schema $defs") if isinstance(definitions_value, Mapping) else {}
    )
    return _schema_node_proves_object(schema, definitions, frozenset())


def _schema_node_proves_object(
    schema: object,
    definitions: Mapping[str, object],
    seen_refs: frozenset[str],
) -> bool:
    if isinstance(schema, bool) or not isinstance(schema, Mapping):
        return False
    node = _string_mapping(schema, "JSON Schema")
    declared_type = node.get("type")
    if declared_type == "object":
        return True
    reference = node.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        name = reference.removeprefix("#/$defs/")
        if "/" not in name and name not in seen_refs and name in definitions:
            return _schema_node_proves_object(definitions[name], definitions, seen_refs | {name})
    for keyword in ("oneOf", "anyOf"):
        branches = node.get(keyword)
        if isinstance(branches, Sequence) and not isinstance(branches, str | bytes):
            return bool(branches) and all(
                _schema_node_proves_object(branch, definitions, seen_refs) for branch in branches
            )
    all_of = node.get("allOf")
    if isinstance(all_of, Sequence) and not isinstance(all_of, str | bytes):
        return bool(all_of) and any(_schema_node_proves_object(branch, definitions, seen_refs) for branch in all_of)
    return False


def _normalize_schema_node(schema: object) -> object:
    if isinstance(schema, bool):
        return schema
    if not isinstance(schema, Mapping):
        raise JsonBoundaryError("A JSON Schema child must be an object or boolean.")
    schema_mapping = _string_mapping(schema, "JSON Schema")

    normalized: dict[str, object] = {}
    for key, value in schema_mapping.items():
        if key == "title":
            continue
        set_value = _normalize_schema_set_keyword(key, value)
        if set_value is not _SCHEMA_KEYWORD_UNHANDLED:
            normalized[key] = set_value
        elif key in _SCHEMA_MAP_KEYWORDS and isinstance(value, Mapping):
            normalized[key] = {
                child_name: _normalize_schema_node(child_schema)
                for child_name, child_schema in _string_mapping(value, f"JSON Schema {key}").items()
            }
        elif key in _SCHEMA_ARRAY_KEYWORDS and isinstance(value, list):
            normalized[key] = [_normalize_schema_node(child) for child in value]
        elif key in _SCHEMA_SINGLE_KEYWORDS and isinstance(value, Mapping | bool):
            normalized[key] = _normalize_schema_node(value)
        elif key == "dependencies" and isinstance(value, Mapping):
            normalized[key] = {
                child_name: (_normalize_schema_node(child) if isinstance(child, Mapping | bool) else child)
                for child_name, child in _string_mapping(value, "JSON Schema dependencies").items()
            }
        else:
            normalized[key] = value
    _close_structured_object_schema(normalized)
    return normalized


def _close_structured_object_schema(schema: dict[str, object]) -> None:
    if schema.get("type") != "object":
        return
    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], Mapping | bool):
        raise JsonBoundaryError("JSON Schema additionalProperties must be a schema object or boolean.")
    if "properties" in schema and "additionalProperties" in schema and schema["additionalProperties"] is not False:
        raise JsonBoundaryError(
            "Structured object boundaries cannot allow undeclared properties; use "
            "an explicit dict[str, T] field for open data."
        )
    if "additionalProperties" not in schema:
        schema["additionalProperties"] = False


def _require_lossless_core_schema(schema: object, seen: set[int] | None = None) -> None:
    """Reject Python adapters whose JSON projection cannot preserve JSON semantics."""

    visited = seen if seen is not None else set()
    pending = [schema]
    while pending:
        current = pending.pop()
        if isinstance(current, Mapping):
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
            schema_mapping = cast(Mapping[str, object], current)
            schema_type = schema_mapping.get("type")
            if schema_type in {"set", "frozenset", "generator"}:
                raise JsonBoundaryError(
                    "Set, frozenset, and one-shot iterable boundary types are not "
                    "supported because they cannot preserve concrete JSON-array "
                    "semantics."
                )
            if schema_type == "dict":
                key_schema = schema_mapping.get("keys_schema")
                if isinstance(key_schema, Mapping) and cast(Mapping[str, object], key_schema).get("type") != "str":
                    raise JsonBoundaryError("Typed JSON object names must map directly to Python str keys.")
            pending.extend(schema_mapping.values())
        elif isinstance(current, Sequence) and not isinstance(current, str | bytes):
            pending.extend(current)


def _normalize_schema_set_keyword(key: str, value: object) -> object:
    if key in {"required", "type"} and isinstance(value, list):
        return _sorted_distinct_strings(value, f"JSON Schema {key}")
    if key == "enum" and isinstance(value, list):
        return _sorted_distinct_json_values(value, "JSON Schema enum")
    if key == "dependentRequired" and isinstance(value, Mapping):
        return {
            child_name: _sorted_distinct_strings(child_value, f"JSON Schema dependentRequired.{child_name}")
            if isinstance(child_value, list)
            else child_value
            for child_name, child_value in _string_mapping(value, "JSON Schema dependentRequired").items()
        }
    return _SCHEMA_KEYWORD_UNHANDLED


def _string_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise JsonBoundaryError(f"{name} must be an object.")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise JsonBoundaryError(f"{name} keys must be strings.")
        result[key] = item
    return result


def _sorted_distinct_strings(value: Sequence[object], name: str) -> list[str]:
    if any(not isinstance(item, str) for item in value):
        raise JsonBoundaryError(f"{name} values must be strings.")
    strings = cast(Sequence[str], value)
    if len(strings) != len(set(strings)):
        raise JsonBoundaryError(f"{name} values must be unique.")
    return sorted(strings)


def _sorted_distinct_json_values(value: Sequence[object], name: str) -> list[object]:
    keyed = [(rfc8785.dumps(normalize_json(item)), item) for item in value]
    if len(keyed) != len({key for key, _item in keyed}):
        raise JsonBoundaryError(f"{name} values must be unique.")
    return [item for _key, item in sorted(keyed, key=lambda entry: entry[0])]


class _LocalDefinitionNormalizer:
    """Rename reachable local definitions by deterministic semantic encounter order."""

    def __init__(self, schema: dict[str, object]) -> None:
        self._definitions: dict[tuple[str, str], object] = {}
        for keyword in ("$defs", "definitions"):
            definitions = schema.get(keyword, {})
            if not isinstance(definitions, Mapping):
                raise JsonBoundaryError(f"JSON Schema {keyword} must be an object.")
            for name, definition in _string_mapping(definitions, f"JSON Schema {keyword}").items():
                self._definitions[(keyword, name)] = definition
        self._root = {key: value for key, value in schema.items() if key not in {"$defs", "definitions"}}
        self._names: dict[tuple[str, str], str] = {}
        self._normalized_definitions: dict[str, object] = {}

    def normalize(self) -> dict[str, object]:
        normalized_value = self._rewrite_schema(self._root)
        if not isinstance(normalized_value, dict):
            raise JsonBoundaryError("Generated JSON Schema must be an object.")
        normalized = cast(dict[str, object], normalized_value)
        if self._normalized_definitions:
            normalized["$defs"] = dict(self._normalized_definitions)
        return normalized

    def _rewrite_schema(self, schema: object) -> object:
        if isinstance(schema, bool):
            return schema
        if not isinstance(schema, Mapping):
            raise JsonBoundaryError("A JSON Schema child must be an object or boolean.")
        schema_mapping = _string_mapping(schema, "JSON Schema")

        rewritten: dict[str, object] = {}
        for key in sorted(schema_mapping):
            value = schema_mapping[key]
            if key in {"$ref", "$dynamicRef"} and isinstance(value, str):
                rewritten[key] = self._rewrite_ref(value)
            elif key == "discriminator" and isinstance(value, Mapping):
                rewritten[key] = self._rewrite_discriminator(value)
            elif key in _SCHEMA_MAP_KEYWORDS and isinstance(value, Mapping):
                children = _string_mapping(value, f"JSON Schema {key}")
                rewritten[key] = {
                    child_name: self._rewrite_schema(children[child_name]) for child_name in sorted(children)
                }
            elif key in _SCHEMA_ARRAY_KEYWORDS and isinstance(value, list):
                rewritten[key] = [self._rewrite_schema(child) for child in value]
            elif key in _SCHEMA_SINGLE_KEYWORDS and isinstance(value, Mapping | bool):
                rewritten[key] = self._rewrite_schema(value)
            elif key == "dependencies" and isinstance(value, Mapping):
                dependencies = _string_mapping(value, "JSON Schema dependencies")
                rewritten[key] = {
                    child_name: (
                        self._rewrite_schema(dependencies[child_name])
                        if isinstance(dependencies[child_name], Mapping | bool)
                        else dependencies[child_name]
                    )
                    for child_name in sorted(dependencies)
                }
            else:
                rewritten[key] = value
        return rewritten

    def _rewrite_discriminator(self, value: object) -> dict[str, object]:
        discriminator = _string_mapping(value, "JSON Schema discriminator")
        rewritten: dict[str, object] = {}
        for key in sorted(discriminator):
            item = discriminator[key]
            if key == "mapping" and isinstance(item, Mapping):
                mapping = _string_mapping(item, "JSON Schema discriminator mapping")
                rewritten[key] = {
                    name: self._rewrite_ref(reference) if isinstance(reference, str) else reference
                    for name, reference in sorted(mapping.items())
                }
            else:
                rewritten[key] = item
        return rewritten

    def _rewrite_ref(self, reference: str) -> str:
        prefixes = (("$defs", "#/$defs/"), ("definitions", "#/definitions/"))
        source = next(
            ((keyword, prefix) for keyword, prefix in prefixes if reference.startswith(prefix)),
            None,
        )
        if source is None:
            return reference
        keyword, prefix = source

        pointer = reference[len(prefix) :]
        encoded_name, separator, suffix = pointer.partition("/")
        definition_name = encoded_name.replace("~1", "/").replace("~0", "~")
        definition_key = (keyword, definition_name)
        if definition_key not in self._definitions:
            raise JsonBoundaryError(f"Local JSON Schema reference has no definition: {reference}")

        normalized_name = self._names.get(definition_key)
        if normalized_name is None:
            normalized_name = f"d{len(self._names)}"
            self._names[definition_key] = normalized_name
            self._normalized_definitions[normalized_name] = True
            self._normalized_definitions[normalized_name] = self._rewrite_schema(self._definitions[definition_key])

        rewritten = f"#/$defs/{normalized_name}"
        if separator:
            rewritten = f"{rewritten}/{suffix}"
        return rewritten
