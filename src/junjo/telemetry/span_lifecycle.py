from __future__ import annotations

import asyncio

from opentelemetry import trace
from opentelemetry.trace import Span


def mark_span_failed(span: Span, exc: Exception) -> None:
    """Annotate a span as failed using standard OpenTelemetry error fields."""

    span.set_attribute("error.type", get_error_type(exc))
    span.set_status(trace.StatusCode.ERROR, str(exc))


def mark_span_cancelled(span: Span, exc: asyncio.CancelledError) -> None:
    """Annotate a span as cancelled without treating cancellation as an error."""

    reason = str(exc.args[0]) if exc.args else "cancelled"
    span.set_attribute("junjo.cancelled", True)
    span.set_attribute("junjo.cancelled_reason", reason)


def get_error_type(exc: BaseException) -> str:
    """Return the stable OpenTelemetry ``error.type`` value for an exception."""

    return type(exc).__name__


def get_span_identifiers(span: Span) -> tuple[str, str]:
    context = span.get_span_context()
    return (
        format(context.trace_id, "032x"),
        format(context.span_id, "016x"),
    )


def get_current_span_identifiers() -> tuple[str, str]:
    return get_span_identifiers(trace.get_current_span())
