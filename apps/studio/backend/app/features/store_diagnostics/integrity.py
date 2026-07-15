"""Generic OTLP evidence-integrity assembly for semantic diagnostics."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.features.store_diagnostics.schemas import (
    EvidenceDiagnostic,
    EvidenceIntegrity,
    EvidenceLossCounts,
)
from app.features.telemetry_contract.scalars import (
    MAX_IJSON_INTEGER,
    is_contract_int,
    is_uint64_decimal,
    portable_diagnostic_text,
)


def _diagnostic(code: str, path: str, message: str) -> EvidenceDiagnostic:
    return EvidenceDiagnostic(
        code=portable_diagnostic_text(code, fallback="invalid_evidence"),
        path=portable_diagnostic_text(path, fallback="evidence"),
        message=portable_diagnostic_text(
            message,
            fallback="Evidence contains nonportable diagnostic text.",
        ),
    )


def assemble_evidence_integrity(
    spans: list[dict[str, Any]],
    diagnostics: list[EvidenceDiagnostic],
) -> EvidenceIntegrity:
    """Return one verdict after validating all preserved OTLP loss evidence."""
    totals = Counter(
        resource_dropped_attributes=0,
        span_dropped_attributes=0,
        span_dropped_events=0,
        span_dropped_links=0,
        event_dropped_attributes=0,
    )
    mapping = {
        "resource_dropped_attributes_count": "resource_dropped_attributes",
        "dropped_attributes_count": "span_dropped_attributes",
        "dropped_events_count": "span_dropped_events",
        "dropped_links_count": "span_dropped_links",
    }
    for span_index, span in enumerate(spans):
        for raw_key, target in mapping.items():
            if raw_key not in span:
                diagnostics.append(
                    _diagnostic(
                        "missing_loss_counter",
                        f"spans[{span_index}].{raw_key}",
                        "Required OTLP loss counter is absent.",
                    )
                )
                continue
            value = span[raw_key]
            if not is_contract_int(value):
                diagnostics.append(
                    _diagnostic(
                        "invalid_loss_counter",
                        f"spans[{span_index}].{raw_key}",
                        "OTLP loss counter is invalid.",
                    )
                )
                continue
            if totals[target] > MAX_IJSON_INTEGER - value:
                diagnostics.append(
                    _diagnostic(
                        "invalid_loss_counter",
                        f"spans[{span_index}].{raw_key}",
                        "Aggregated OTLP loss counter exceeds the portable integer domain.",
                    )
                )
                continue
            totals[target] += value

        events = span.get("events_json")
        if not isinstance(events, list):
            diagnostics.append(
                _diagnostic(
                    "missing_loss_counter",
                    f"spans[{span_index}].events_json",
                    "Required event evidence is absent.",
                )
            )
            continue
        for event_index, event in enumerate(events):
            path = f"spans[{span_index}].events[{event_index}]"
            if not isinstance(event, dict):
                diagnostics.append(
                    _diagnostic(
                        "missing_loss_counter",
                        path,
                        "Required event evidence is absent.",
                    )
                )
                continue
            if not is_uint64_decimal(event.get("timeUnixNano")):
                diagnostics.append(
                    _diagnostic(
                        "invalid_event_timestamp",
                        f"{path}.timeUnixNano",
                        "Event timestamp must be exact canonical uint64 decimal text.",
                    )
                )
            if "droppedAttributesCount" not in event:
                diagnostics.append(
                    _diagnostic(
                        "missing_loss_counter",
                        path,
                        "Required event loss counter is absent.",
                    )
                )
                continue
            value = event["droppedAttributesCount"]
            if not is_contract_int(value):
                diagnostics.append(
                    _diagnostic(
                        "invalid_loss_counter",
                        path,
                        "Event loss counter is invalid.",
                    )
                )
                continue
            if totals["event_dropped_attributes"] > MAX_IJSON_INTEGER - value:
                diagnostics.append(
                    _diagnostic(
                        "invalid_loss_counter",
                        path,
                        "Aggregated event loss counter exceeds the portable integer domain.",
                    )
                )
                continue
            totals["event_dropped_attributes"] += value

    loss_counts = EvidenceLossCounts(**totals)
    return EvidenceIntegrity(
        status=(
            "partial"
            if diagnostics or any(value > 0 for value in loss_counts.model_dump().values())
            else "complete"
        ),
        diagnostics=diagnostics,
        loss_counts=loss_counts,
    )
