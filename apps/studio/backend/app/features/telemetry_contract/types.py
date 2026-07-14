"""Pydantic scalar types for Studio's interoperable semantic APIs."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, Field

from app.features.telemetry_contract.scalars import MAX_IJSON_INTEGER, is_portable_text


def _require_portable_text(value: str) -> str:
    if not is_portable_text(value):
        raise ValueError("text must contain only Unicode scalar values")
    return value


PortableText = Annotated[str, AfterValidator(_require_portable_text)]
NonEmptyPortableText = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(_require_portable_text),
]
SafeNonNegativeInt = Annotated[int, Field(ge=0, le=MAX_IJSON_INTEGER)]
SafePositiveInt = Annotated[int, Field(ge=1, le=MAX_IJSON_INTEGER)]
