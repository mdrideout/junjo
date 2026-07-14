"""Strict parsing of telemetry payload-slot evidence."""

from __future__ import annotations

import json
import math
from typing import Any

from app.features.store_diagnostics.schemas import EvidenceDiagnostic, PayloadEvidence
from app.features.telemetry_contract.scalars import (
    is_portable_enum,
    is_portable_text,
    portable_diagnostic_text,
)

EMITTED_MODES = {"full", "redacted", "excluded", "reference"}


class DuplicateJsonObjectNameError(ValueError):
    """A JSON object repeated one member name and is not contract-safe."""


class NonPortableJsonValueError(ValueError):
    """A decoded value is outside the shared I-JSON interoperability domain."""


class PayloadNestingDepthError(ValueError):
    """A decoded payload exceeds the contract's interoperable nesting bound."""


_SAFE_INTEGER_MAX = 2**53 - 1
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
                if not isinstance(key, str):
                    raise NonPortableJsonValueError(
                        f"non-string object key at {current_path}"
                    )
                pending.append((key, f"{current_path}.<key>", depth + 1))
                pending.append((item, f"{current_path}.{key}", depth + 1))
            continue
        raise NonPortableJsonValueError(f"unsupported JSON value at {current_path}")


def _reject_nonfinite_json(token: str) -> None:
    raise ValueError(f"non-finite JSON number {token!r}")


def _reject_duplicate_names(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateJsonObjectNameError(f"duplicate JSON object name {key!r}")
        value[key] = item
    return value


def decode_json_value(raw: str) -> Any:
    """Decode strict finite JSON without silently collapsing duplicate names."""
    try:
        value = json.loads(
            raw,
            parse_constant=_reject_nonfinite_json,
            object_pairs_hook=_reject_duplicate_names,
        )
    except RecursionError as error:
        raise PayloadNestingDepthError(
            f"JSON nesting exceeds {MAX_JSON_NESTING_DEPTH}"
        ) from error
    _validate_portable_json(value)
    return value


def missing_payload(root: str, reason: str) -> tuple[PayloadEvidence, list[EvidenceDiagnostic]]:
    """Represent absent required evidence without inventing contract content."""
    safe_root = portable_diagnostic_text(root, fallback="payload")
    safe_reason = portable_diagnostic_text(
        reason,
        fallback="Payload evidence contains nonportable diagnostic text.",
    )
    diagnostic = EvidenceDiagnostic(
        code="required_payload_slot_missing",
        path=safe_root,
        message=safe_reason,
    )
    return (
        PayloadEvidence(
            mode="missing",
            policy=None,
            value=None,
            reference=None,
            reason=safe_reason,
        ),
        [diagnostic],
    )


def parse_payload_slot(
    attributes: dict[str, Any], root: str, *, required: bool
) -> tuple[PayloadEvidence | None, list[EvidenceDiagnostic]]:
    """Parse one payload slot while retaining malformed evidence as diagnostics."""
    mode = attributes.get(f"{root}.mode")
    policy = attributes.get(f"{root}.policy")
    if (
        mode is None
        and policy is None
        and root not in attributes
        and f"{root}.reference" not in attributes
    ):
        if not required:
            return None, []
        return missing_payload(root, f"Required payload slot {root!r} is absent.")

    diagnostics: list[EvidenceDiagnostic] = []
    if not is_portable_enum(mode, EMITTED_MODES):
        payload, missing = missing_payload(root, f"Payload mode {mode!r} is invalid.")
        missing[0].code = "invalid_payload_slot"
        return payload, missing
    if not is_portable_text(policy, nonempty=True):
        payload, missing = missing_payload(root, "Payload policy is absent or invalid.")
        if isinstance(policy, str) and policy:
            missing[0].code = "nonportable_scalar_text"
        return payload, missing

    content_present = root in attributes
    reference_present = f"{root}.reference" in attributes
    value: Any | None = None
    reference: str | None = None
    if mode == "full" or mode == "redacted":
        if not content_present or reference_present or not isinstance(attributes.get(root), str):
            payload, missing = missing_payload(
                root, "Payload content/reference does not match mode."
            )
            missing[0].code = "invalid_payload_slot"
            return payload, missing
        try:
            value = decode_json_value(attributes[root])
        except DuplicateJsonObjectNameError:
            payload, missing = missing_payload(root, "Payload JSON repeats an object name.")
            missing[0].code = "duplicate_json_object_name"
            return payload, missing
        except NonPortableJsonValueError:
            payload, missing = missing_payload(root, "Payload JSON is outside the I-JSON domain.")
            missing[0].code = "nonportable_json_value"
            return payload, missing
        except PayloadNestingDepthError:
            payload, missing = missing_payload(
                root,
                f"Payload JSON exceeds the maximum nesting depth of {MAX_JSON_NESTING_DEPTH}.",
            )
            missing[0].code = "payload_nesting_too_deep"
            return payload, missing
        except (json.JSONDecodeError, ValueError):
            payload, missing = missing_payload(root, "Payload content is not valid JSON.")
            missing[0].code = "invalid_payload_json"
            return payload, missing
    elif mode == "reference":
        raw_reference = attributes.get(f"{root}.reference")
        if content_present or not is_portable_text(raw_reference, nonempty=True):
            payload, missing = missing_payload(root, "Reference payload is invalid.")
            missing[0].code = (
                "nonportable_scalar_text"
                if isinstance(raw_reference, str) and raw_reference
                else "invalid_payload_slot"
            )
            return payload, missing
        reference = raw_reference
    elif content_present or reference_present:
        payload, missing = missing_payload(root, "Excluded payload unexpectedly has content.")
        missing[0].code = "invalid_payload_slot"
        return payload, missing

    return (
        PayloadEvidence(
            mode=mode,
            policy=policy,
            value=value,
            reference=reference,
            reason=None,
        ),
        diagnostics,
    )
