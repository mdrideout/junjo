"""Task-local exact evidence capture for external OpenAI Agent spans."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field

from opentelemetry.trace import SpanContext

from ...studio import OpenTelemetrySpanReference


@dataclass(slots=True)
class OpenAIAgentEvidenceCapture:
    """One task-local request for exact external Agent span evidence."""

    expected_agent_name: str
    evidence: list[OpenTelemetrySpanReference] = field(default_factory=list)


_ACTIVE_CAPTURE: ContextVar[OpenAIAgentEvidenceCapture | None] = ContextVar(
    "junjo_openai_agent_evidence_capture",
    default=None,
)


@contextmanager
def capture_openai_agent_evidence(expected_agent_name: str) -> Iterator[OpenAIAgentEvidenceCapture]:
    """Capture matching evidence emitted in this task and its child tasks."""

    capture = OpenAIAgentEvidenceCapture(expected_agent_name=expected_agent_name)
    token: Token[OpenAIAgentEvidenceCapture | None] = _ACTIVE_CAPTURE.set(capture)
    try:
        yield capture
    finally:
        _ACTIVE_CAPTURE.reset(token)


def record_openai_agent_evidence(
    *,
    agent_name: str,
    span_context: SpanContext,
    resource_attributes: Mapping[str, object],
) -> None:
    """Record one exact translated Agent span for the active evaluation target."""

    capture = _ACTIVE_CAPTURE.get()
    if capture is None or capture.expected_agent_name != agent_name or not span_context.is_valid:
        return

    service_name = resource_attributes.get("service.name")
    if not isinstance(service_name, str) or not service_name:
        return
    service_namespace = resource_attributes.get("service.namespace", "")
    if not isinstance(service_namespace, str):
        service_namespace = ""

    capture.evidence.append(
        OpenTelemetrySpanReference(
            service_namespace=service_namespace,
            service_name=service_name,
            trace_id=format(span_context.trace_id, "032x"),
            span_id=format(span_context.span_id, "016x"),
        )
    )


__all__ = [
    "OpenAIAgentEvidenceCapture",
    "capture_openai_agent_evidence",
    "record_openai_agent_evidence",
]
