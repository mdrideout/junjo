"""Pydantic-backed Agent value normalization boundaries."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import fields, is_dataclass
from typing import cast

import rfc8785
from pydantic import BaseModel, TypeAdapter

from .._json import (
    FrozenJsonValue,
    JsonBoundaryError,
    JsonNestingDepthError,
    freeze_json,
    json_dumps,
)


def json_candidate(value: object) -> FrozenJsonValue:
    """Capture concrete portable JSON without applying a declared serializer."""

    try:
        _reject_one_shot_iterators(value)
        return freeze_json(value)
    except Exception as exc:
        raise JsonBoundaryError(f"Value of type {type(value).__name__} is not portable JSON.") from exc


def _reject_one_shot_iterators(value: object, seen: set[int] | None = None) -> None:
    """Reject values whose diagnostic capture would consume application state."""

    visited = seen if seen is not None else set()
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, Iterator):
            raise JsonBoundaryError("One-shot iterators are not portable JSON values.")
        identity = id(current)
        if identity in visited:
            continue
        visited.add(identity)
        pending.extend(_projection_children(current))


def _projection_children(value: object) -> Iterable[object]:
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise JsonBoundaryError("Portable JSON object keys must be strings.")
        return value.values()
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return value
    if isinstance(value, BaseModel):
        extra = getattr(value, "__pydantic_extra__", None)
        return (
            *value.__dict__.values(),
            *((extra,) if isinstance(extra, Mapping) else ()),
        )
    if is_dataclass(value) and not isinstance(value, type):
        return tuple(getattr(value, field.name) for field in fields(value))
    return ()


def validate_and_detach(adapter: TypeAdapter, value: object) -> tuple[object, FrozenJsonValue]:
    """Validate a declared boundary and return typed and normalized detached values."""

    _reject_one_shot_iterators(value)
    try:
        candidate = freeze_json(value)
    except JsonNestingDepthError:
        raise
    except JsonBoundaryError:
        candidate = None
        validated = adapter.validate_python(
            value,
            strict=True,
            extra="forbid",
            by_alias=True,
            by_name=False,
        )
    else:
        validated = adapter.validate_json(
            json_dumps(candidate),
            strict=True,
            extra="forbid",
            by_alias=True,
            by_name=False,
        )
    normalized = freeze_json(adapter.dump_python(validated, mode="json", by_alias=True))
    if candidate is not None:
        _require_candidate_preserved(candidate, normalized)
    detached = adapter.validate_json(
        json_dumps(normalized),
        strict=True,
        extra="forbid",
        by_alias=True,
        by_name=False,
    )
    if candidate is None:
        _require_typed_value_preserved(validated, detached)
    round_tripped = freeze_json(adapter.dump_python(detached, mode="json", by_alias=True))
    if json_dumps(round_tripped) != json_dumps(normalized):
        raise JsonBoundaryError("Declared boundary serialization must be stable after one strict JSON round trip.")
    return detached, normalized


def _require_typed_value_preserved(validated: object, detached: object) -> None:
    """Reject a typed serializer that loses or rewrites declared Python data."""

    if type(validated) is not type(detached):
        raise JsonBoundaryError("Declared boundary serialization changed the validated Python type.")
    try:
        equal = validated == detached
    except Exception as exc:
        raise JsonBoundaryError("Declared boundary values must support deterministic equality.") from exc
    if not isinstance(equal, bool) or not equal:
        raise JsonBoundaryError("Declared boundary serialization changed the validated Python value.")


def _require_candidate_preserved(
    candidate: FrozenJsonValue,
    normalized: FrozenJsonValue,
    *,
    path: str = "$",
) -> None:
    """Allow declared defaults to add members, but never rewrite supplied JSON."""

    if isinstance(candidate, Mapping):
        if not isinstance(normalized, Mapping):
            raise JsonBoundaryError(f"Declared validation changed {path} from an object.")
        candidate_mapping = cast(Mapping[str, FrozenJsonValue], candidate)
        normalized_mapping = cast(Mapping[str, FrozenJsonValue], normalized)
        for key, candidate_value in candidate_mapping.items():
            if key not in normalized_mapping:
                raise JsonBoundaryError(f"Declared validation removed supplied member {path}.{key}.")
            _require_candidate_preserved(
                candidate_value,
                normalized_mapping[key],
                path=f"{path}.{key}",
            )
        return
    if isinstance(candidate, tuple):
        if not isinstance(normalized, tuple) or len(candidate) != len(normalized):
            raise JsonBoundaryError(f"Declared validation changed the length or kind of array {path}.")
        for index, (candidate_value, normalized_value) in enumerate(zip(candidate, normalized, strict=True)):
            _require_candidate_preserved(
                candidate_value,
                normalized_value,
                path=f"{path}[{index}]",
            )
        return
    if isinstance(normalized, Mapping | tuple) or rfc8785.dumps(candidate) != rfc8785.dumps(normalized):
        raise JsonBoundaryError(f"Declared validation changed supplied value {path}.")
