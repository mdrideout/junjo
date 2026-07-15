from __future__ import annotations

import asyncio

from opentelemetry import trace
from opentelemetry.trace import Span

from .diagnostics import (
    cancellation_reason,
    error_type,
    exception_event_type,
    exception_message,
    exception_stacktrace,
)


def mark_span_failed(span: Span, exc: BaseException) -> None:
    """Annotate a span as failed using standard OpenTelemetry error fields."""

    span.set_attribute("error.type", get_error_type(exc))
    span.set_status(trace.StatusCode.ERROR, exception_message(exc))


def mark_span_cancelled(span: Span, exc: asyncio.CancelledError) -> None:
    """Annotate a span as cancelled without treating cancellation as an error."""

    span.set_attribute("junjo.cancelled", True)
    span.set_attribute("junjo.cancelled_reason", cancellation_reason(exc))


def get_error_type(exc: BaseException) -> str:
    """Return the stable OpenTelemetry ``error.type`` value for an exception."""

    return error_type(exc)


def record_span_exception(span: Span, exc: BaseException) -> None:
    """Record a standard exception event without trusting ``exc.__str__``."""

    span.add_event(
        "exception",
        attributes={
            "exception.type": exception_event_type(exc),
            "exception.message": exception_message(exc),
            "exception.stacktrace": exception_stacktrace(exc),
            "exception.escaped": "False",
        },
    )


def get_span_identifiers(span: Span) -> tuple[str, str]:
    """
    Return lowercase hexadecimal OpenTelemetry trace and span identifiers.

    :param span: The span whose context should be formatted.
    :type span: Span
    :returns: ``(trace_id, span_id)`` formatted for logs, hooks, and telemetry
              payloads.
    :rtype: tuple[str, str]
    """
    context = span.get_span_context()
    return (
        format(context.trace_id, "032x"),
        format(context.span_id, "016x"),
    )


def get_current_span_identifiers() -> tuple[str, str]:
    """
    Return formatted identifiers for the currently active OpenTelemetry span.

    :returns: ``(trace_id, span_id)`` for the current span.
    :rtype: tuple[str, str]
    """
    return get_span_identifiers(trace.get_current_span())
