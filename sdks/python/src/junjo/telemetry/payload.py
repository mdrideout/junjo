"""Built-in telemetry payload-slot encoding for contract version 2."""

from __future__ import annotations

from opentelemetry.trace import Span

from .._json import json_dumps

FULL_PAYLOAD_POLICY = "junjo.full.v1"


def encode_json(value: object) -> str:
    """Validate and encode one portable payload as deterministic JSON."""

    return json_dumps(value)


def full_payload_attributes(root: str, value: object) -> dict[str, str]:
    """Build the complete adjacent metadata for one full-evidence slot."""

    return {
        root: encode_json(value),
        f"{root}.mode": "full",
        f"{root}.policy": FULL_PAYLOAD_POLICY,
    }


def set_full_payload(span: Span, root: str, value: object) -> None:
    """Set one full-evidence payload slot on a recording span."""

    for name, encoded in full_payload_attributes(root, value).items():
        span.set_attribute(name, encoded)
