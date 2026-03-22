from __future__ import annotations

import asyncio

from opentelemetry.trace import Span


def mark_span_cancelled(span: Span, exc: asyncio.CancelledError) -> None:
    """Annotate a span as cancelled without treating cancellation as an error."""

    reason = str(exc.args[0]) if exc.args else "cancelled"
    span.set_attribute("junjo.cancelled", True)
    span.set_attribute("junjo.cancelled_reason", reason)
