"""Shared portable JSON validation and immutable ownership helpers."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import TypeAlias, cast

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
FrozenJsonValue: TypeAlias = JsonScalar | tuple["FrozenJsonValue", ...] | Mapping[str, "FrozenJsonValue"]

MAX_IJSON_INTEGER = 9_007_199_254_740_991
MAX_JSON_NESTING_DEPTH = 128


class JsonBoundaryError(ValueError):
    """Raised when a value cannot cross a portable JSON boundary."""


class JsonNestingDepthError(JsonBoundaryError):
    """Raised before recursive processing can exceed the transport depth bound."""


def freeze_json(value: object) -> FrozenJsonValue:
    """Validate I-JSON portability and recursively freeze an owned value."""

    validate_json_nesting(value)
    return _freeze_json(value)


def _freeze_json(value: object) -> FrozenJsonValue:
    """Freeze one value after the iterative depth guard has succeeded."""

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return require_ijson_text(value, "JSON string")
    if isinstance(value, int):
        return require_ijson_integer(value, "JSON integer")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise JsonBoundaryError("JSON numbers must be finite.")
        return value
    if isinstance(value, list | tuple):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, Mapping):
        frozen: dict[str, FrozenJsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise JsonBoundaryError("JSON object keys must be strings.")
            require_ijson_text(key, "JSON object key")
            frozen[key] = _freeze_json(item)
        return MappingProxyType(frozen)
    raise JsonBoundaryError(f"Value of type {type(value).__name__} is not JSON-compatible.")


def validate_json_nesting(value: object) -> None:
    """Enforce the shared depth bound iteratively, counting object names as children."""

    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > MAX_JSON_NESTING_DEPTH:
            raise JsonNestingDepthError(f"JSON nesting must not exceed {MAX_JSON_NESTING_DEPTH}.")
        if isinstance(current, list | tuple):
            pending.extend((item, depth + 1) for item in current)
        elif isinstance(current, Mapping):
            for key, item in current.items():
                pending.append((key, depth + 1))
                pending.append((item, depth + 1))


def thaw_json(value: FrozenJsonValue) -> JsonValue:
    """Return a detached mutable JSON representation of a frozen value."""

    validate_json_nesting(value)
    return _thaw_json(value)


def _thaw_json(value: FrozenJsonValue) -> JsonValue:
    """Thaw one value after the iterative depth guard has succeeded."""

    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise JsonBoundaryError("Frozen JSON object keys must be strings.")
            result[key] = _thaw_json(cast(FrozenJsonValue, item))
        return result
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def normalize_json(value: object) -> JsonValue:
    """Validate and detach one mutable portable JSON projection."""

    return thaw_json(freeze_json(value))


def json_dumps(value: object) -> str:
    """Validate and serialize one portable JSON value deterministically."""

    return json.dumps(
        normalize_json(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def require_ijson_text(value: object, name: str, *, nonempty: bool = False) -> str:
    """Return a portable Unicode string or raise ``JsonBoundaryError``."""

    if not isinstance(value, str):
        requirement = "a non-empty string" if nonempty else "a string"
        raise JsonBoundaryError(f"{name} must be {requirement}.")
    if nonempty and not value:
        raise JsonBoundaryError(f"{name} must be a non-empty string.")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise JsonBoundaryError(f"{name} must not contain lone Unicode surrogates.") from exc
    return value


def require_ijson_integer(
    value: object,
    name: str,
    *,
    minimum: int | None = None,
) -> int:
    """Return an interoperable integer or raise ``JsonBoundaryError``."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise JsonBoundaryError(f"{name} must be an integer.")
    if not -MAX_IJSON_INTEGER <= value <= MAX_IJSON_INTEGER:
        raise JsonBoundaryError(
            f"{name} must be within the interoperable IEEE-754 range [-{MAX_IJSON_INTEGER}, {MAX_IJSON_INTEGER}]."
        )
    if minimum is not None and value < minimum:
        raise JsonBoundaryError(f"{name} must be at least {minimum}.")
    return value
