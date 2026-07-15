"""Deterministic generated-JSON-Schema normalization for Junjo contracts.

This module is intentionally dependency free. It defines the conformance
algorithm exercised by shared fixtures; product runtimes own their own
implementations and must prove equivalence against those fixtures.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from canonical_json import CanonicalizationError
from canonical_json import dumps as canonical_json_dumps


class SchemaNormalizationError(ValueError):
    """Raised when generated schema material is outside the supported profile."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_SCHEMA_MAP_KEYWORDS = frozenset(
    {
        "$defs",
        "definitions",
        "dependentSchemas",
        "patternProperties",
        "properties",
    }
)
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


def normalize_generated_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return the deterministic Junjo generated-schema profile representation."""

    without_titles = _normalize_schema_node(schema)
    if not isinstance(without_titles, dict):
        raise SchemaNormalizationError(
            "invalid_schema_profile", "Generated JSON Schema must be an object."
        )
    return _LocalDefinitionNormalizer(without_titles).normalize()


def _normalize_schema_node(schema: Any) -> Any:
    """Remove ``title`` only when it is a Schema annotation keyword."""

    if isinstance(schema, bool):
        return schema
    if not isinstance(schema, Mapping):
        raise SchemaNormalizationError(
            "invalid_schema_profile",
            "A JSON Schema child must be an object or boolean.",
        )
    schema_mapping = _string_mapping(schema, "JSON Schema")

    normalized: dict[str, Any] = {}
    for key, value in schema_mapping.items():
        if key == "title":
            continue
        if key in {"required", "type"} and isinstance(value, list):
            normalized[key] = _canonical_set(value, f"JSON Schema {key}")
        elif key == "enum" and isinstance(value, list):
            normalized[key] = _canonical_set(value, "JSON Schema enum")
        elif key == "dependentRequired" and isinstance(value, Mapping):
            normalized[key] = {
                child_name: _canonical_set(child, "JSON Schema dependentRequired")
                if isinstance(child, list)
                else child
                for child_name, child in _string_mapping(
                    value, "JSON Schema dependentRequired"
                ).items()
            }
        elif key in _SCHEMA_MAP_KEYWORDS and isinstance(value, Mapping):
            normalized[key] = {
                child_name: _normalize_schema_node(child_schema)
                for child_name, child_schema in _string_mapping(
                    value, f"JSON Schema {key}"
                ).items()
            }
        elif key in _SCHEMA_ARRAY_KEYWORDS and isinstance(value, list):
            normalized[key] = [_normalize_schema_node(child) for child in value]
        elif key in _SCHEMA_SINGLE_KEYWORDS and isinstance(value, (Mapping, bool)):
            normalized[key] = _normalize_schema_node(value)
        elif key == "dependencies" and isinstance(value, Mapping):
            normalized[key] = {
                child_name: (
                    _normalize_schema_node(child)
                    if isinstance(child, (Mapping, bool))
                    else child
                )
                for child_name, child in _string_mapping(
                    value, "JSON Schema dependencies"
                ).items()
            }
        else:
            normalized[key] = value
    _close_structured_object_schema(normalized)
    return normalized


def _close_structured_object_schema(schema: dict[str, Any]) -> None:
    """Close declared object models while preserving explicit dictionary schemas."""

    if schema.get("type") != "object":
        return
    if "additionalProperties" in schema and not isinstance(
        schema["additionalProperties"], (Mapping, bool)
    ):
        raise SchemaNormalizationError(
            "invalid_schema_profile",
            "JSON Schema additionalProperties must be a schema object or boolean.",
        )
    if (
        "properties" in schema
        and "additionalProperties" in schema
        and schema["additionalProperties"] is not False
    ):
        raise SchemaNormalizationError(
            "invalid_schema_profile",
            "Structured object boundaries cannot allow undeclared properties; use "
            "an explicit dictionary field for open data.",
        )
    if "additionalProperties" not in schema:
        schema["additionalProperties"] = False


def _canonical_set(values: list[Any], name: str) -> list[Any]:
    """Canonicalize a JSON-Schema array whose semantics are set-valued."""

    unique: dict[bytes, Any] = {}
    try:
        for value in values:
            unique.setdefault(canonical_json_dumps(value), value)
    except CanonicalizationError as error:
        raise SchemaNormalizationError(
            "nonportable_json_value", f"{name} is outside the I-JSON domain."
        ) from error
    if len(unique) != len(values):
        raise SchemaNormalizationError(
            "duplicate_set_member", f"{name} must not contain duplicate members."
        )
    return [unique[key] for key in sorted(unique)]


def _string_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaNormalizationError("invalid_schema_profile", f"{name} must be an object.")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise SchemaNormalizationError(
                "invalid_schema_profile", f"{name} keys must be strings."
            )
        result[key] = item
    return result


class _LocalDefinitionNormalizer:
    """Rename reachable local definitions by deterministic encounter order."""

    def __init__(self, schema: dict[str, Any]) -> None:
        self._definitions: dict[tuple[str, str], Any] = {}
        for keyword in ("$defs", "definitions"):
            definitions = schema.get(keyword, {})
            if not isinstance(definitions, Mapping):
                raise SchemaNormalizationError(
                    "invalid_schema_profile",
                    f"JSON Schema {keyword} must be an object.",
                )
            for name, definition in _string_mapping(
                definitions, f"JSON Schema {keyword}"
            ).items():
                self._definitions[(keyword, name)] = definition
        self._root = {
            key: value
            for key, value in schema.items()
            if key not in {"$defs", "definitions"}
        }
        self._names: dict[tuple[str, str], str] = {}
        self._normalized_definitions: dict[str, Any] = {}

    def normalize(self) -> dict[str, Any]:
        normalized_value = self._rewrite_schema(self._root)
        if not isinstance(normalized_value, dict):
            raise SchemaNormalizationError(
                "invalid_schema_profile", "Generated JSON Schema must be an object."
            )
        if self._normalized_definitions:
            normalized_value["$defs"] = dict(self._normalized_definitions)
        return normalized_value

    def _rewrite_schema(self, schema: Any) -> Any:
        if isinstance(schema, bool):
            return schema
        if not isinstance(schema, Mapping):
            raise SchemaNormalizationError(
                "invalid_schema_profile",
                "A JSON Schema child must be an object or boolean.",
            )
        schema_mapping = _string_mapping(schema, "JSON Schema")

        rewritten: dict[str, Any] = {}
        for key in sorted(schema_mapping):
            value = schema_mapping[key]
            if key in {"$ref", "$dynamicRef"} and isinstance(value, str):
                rewritten[key] = self._rewrite_ref(value)
            elif key == "discriminator" and isinstance(value, Mapping):
                rewritten[key] = self._rewrite_discriminator(value)
            elif key in _SCHEMA_MAP_KEYWORDS and isinstance(value, Mapping):
                children = _string_mapping(value, f"JSON Schema {key}")
                rewritten[key] = {
                    child_name: self._rewrite_schema(children[child_name])
                    for child_name in sorted(children)
                }
            elif key in _SCHEMA_ARRAY_KEYWORDS and isinstance(value, list):
                rewritten[key] = [self._rewrite_schema(child) for child in value]
            elif key in _SCHEMA_SINGLE_KEYWORDS and isinstance(value, (Mapping, bool)):
                rewritten[key] = self._rewrite_schema(value)
            elif key == "dependencies" and isinstance(value, Mapping):
                dependencies = _string_mapping(value, "JSON Schema dependencies")
                rewritten[key] = {
                    child_name: (
                        self._rewrite_schema(dependencies[child_name])
                        if isinstance(dependencies[child_name], (Mapping, bool))
                        else dependencies[child_name]
                    )
                    for child_name in sorted(dependencies)
                }
            elif key == "dependentRequired" and isinstance(value, Mapping):
                required = _string_mapping(value, "JSON Schema dependentRequired")
                rewritten[key] = {
                    child_name: required[child_name]
                    for child_name in sorted(required)
                }
            else:
                rewritten[key] = value
        return rewritten

    def _rewrite_discriminator(self, value: Any) -> dict[str, Any]:
        discriminator = _string_mapping(value, "JSON Schema discriminator")
        rewritten: dict[str, Any] = {}
        for key in sorted(discriminator):
            item = discriminator[key]
            if key == "mapping" and isinstance(item, Mapping):
                mapping = _string_mapping(item, "JSON Schema discriminator mapping")
                rewritten[key] = {
                    name: self._rewrite_ref(reference)
                    if isinstance(reference, str)
                    else reference
                    for name, reference in sorted(mapping.items())
                }
            else:
                rewritten[key] = item
        return rewritten

    def _rewrite_ref(self, reference: str) -> str:
        prefixes = (("$defs", "#/$defs/"), ("definitions", "#/definitions/"))
        source = next(
            (
                (keyword, prefix)
                for keyword, prefix in prefixes
                if reference.startswith(prefix)
            ),
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
            raise SchemaNormalizationError(
                "unresolved_local_reference",
                f"Local JSON Schema reference has no definition: {reference}"
            )

        normalized_name = self._names.get(definition_key)
        if normalized_name is None:
            normalized_name = f"d{len(self._names)}"
            self._names[definition_key] = normalized_name
            # Preassign before recursion so self-references and cycles terminate.
            self._normalized_definitions[normalized_name] = True
            self._normalized_definitions[normalized_name] = self._rewrite_schema(
                self._definitions[definition_key]
            )

        rewritten = f"#/$defs/{normalized_name}"
        if separator:
            rewritten = f"{rewritten}/{suffix}"
        return rewritten
