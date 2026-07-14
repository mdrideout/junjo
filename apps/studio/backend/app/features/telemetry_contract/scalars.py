"""Portable scalar-domain predicates shared by semantic telemetry consumers."""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Any

ACTIVE_TELEMETRY_CONTRACT_VERSION = 2
MAX_IJSON_INTEGER = 9_007_199_254_740_991
MAX_UINT64 = 18_446_744_073_709_551_615


def is_contract_int(value: Any, *, minimum: int = 0) -> bool:
    """Reject bool-as-int and integers unsafe for interoperable JSON consumers."""
    return type(value) is int and minimum <= value <= MAX_IJSON_INTEGER


def is_portable_text(value: Any, *, nonempty: bool = False) -> bool:
    """Return whether a scalar is Unicode text encodable as strict UTF-8."""
    if not isinstance(value, str) or (nonempty and not value):
        return False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return True


def is_portable_enum(value: Any, allowed: Collection[str]) -> bool:
    """Validate untrusted text before any membership operation."""

    return is_portable_text(value, nonempty=True) and value in allowed


def is_lower_hex(value: Any, *, length: int) -> bool:
    """Validate one exact lowercase hexadecimal transport identity."""
    return (
        isinstance(value, str)
        and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None
    )


def is_active_contract_version(value: Any) -> bool:
    """Recognize exactly the active semantic telemetry contract version."""

    return type(value) is int and value == ACTIVE_TELEMETRY_CONTRACT_VERSION


def is_uint64_decimal(value: Any) -> bool:
    """Validate canonical decimal text for an unsigned 64-bit scalar."""
    return (
        isinstance(value, str)
        and re.fullmatch(r"(?:0|[1-9][0-9]{0,19})", value) is not None
        and int(value) <= MAX_UINT64
    )


def portable_diagnostic_text(value: Any, *, fallback: str) -> str:
    """Keep diagnostic serialization fail-closed when evidence contains bad text."""
    return value if is_portable_text(value, nonempty=True) else fallback


def span_evidence_path(
    span: dict[str, Any],
    suffix: str = "",
    *,
    index: int | None = None,
) -> str:
    """Build a diagnostic path without interpolating an untrusted span identity."""
    span_id = span.get("span_id")
    if is_lower_hex(span_id, length=16):
        base = f"span[{span_id}]"
    elif index is not None:
        base = f"spans[{index}]"
    else:
        base = "span[unidentified]"
    return f"{base}.{suffix}" if suffix else base
