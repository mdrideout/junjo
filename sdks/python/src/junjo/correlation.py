"""Application-owned correlation propagated across one Junjo execution tree."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from opentelemetry.trace import Span

from ._json import require_ijson_text


@dataclass(frozen=True, slots=True)
class ExecutionCorrelation:
    """Immutable application identity attached to executable owner spans.

    Correlation identifies the trusted application action that caused an
    execution tree. It remains distinct from Junjo runtime IDs and physical
    OpenTelemetry trace/span IDs. A correlation passed to a top-level
    :class:`~junjo.workflow.Workflow` or :class:`~junjo.agent.Agent` is
    inherited by nested Junjo executables automatically.

    :param type: Portable non-empty application-defined identity type, such as
        ``"ai_chat.turn"``.
    :type type: str
    :param id: Portable non-empty application-owned identity.
    :type id: str
    """

    type: str
    id: str

    def __post_init__(self) -> None:
        require_ijson_text(self.type, "Execution correlation type", nonempty=True)
        require_ijson_text(self.id, "Execution correlation id", nonempty=True)


_ACTIVE_EXECUTION_CORRELATION: ContextVar[ExecutionCorrelation | None] = ContextVar(
    "junjo_active_execution_correlation",
    default=None,
)


def _resolve_execution_correlation(
    requested: ExecutionCorrelation | None,
) -> ExecutionCorrelation | None:
    active = _ACTIVE_EXECUTION_CORRELATION.get()
    if active is not None and requested is not None and active != requested:
        raise ValueError("A nested Junjo executable cannot replace the active correlation.")
    return requested if requested is not None else active


def _get_active_execution_correlation() -> ExecutionCorrelation | None:
    return _ACTIVE_EXECUTION_CORRELATION.get()


@contextmanager
def _active_execution_correlation(correlation: ExecutionCorrelation | None):
    token = _ACTIVE_EXECUTION_CORRELATION.set(correlation)
    try:
        yield
    finally:
        _ACTIVE_EXECUTION_CORRELATION.reset(token)


def _set_correlation_span_attributes(
    span: Span,
    correlation: ExecutionCorrelation | None,
) -> None:
    if correlation is None:
        return
    span.set_attribute("junjo.correlation.type", correlation.type)
    span.set_attribute("junjo.correlation.id", correlation.id)
