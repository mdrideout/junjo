"""OpenAI Agents TraceProvider wrapper that emits corresponding OpenTelemetry spans."""

from __future__ import annotations

import logging
from contextvars import Token
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from time import time_ns
from typing import Any, Generic, TypeVar

from agents.tracing import Span as OpenAISpan
from agents.tracing import Trace as OpenAITrace
from agents.tracing import TraceProvider as OpenAITraceProvider
from agents.tracing import TracingProcessor
from agents.tracing.config import TracingConfig
from agents.tracing.span_data import AgentSpanData, SpanData
from agents.tracing.spans import SpanError
from opentelemetry import context as otel_context
from opentelemetry.context import Context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Span as OpenTelemetrySpan
from opentelemetry.trace import SpanKind, Status, StatusCode, set_span_in_context

from ._evidence import record_openai_agent_evidence
from ._span_mapping import (
    TRANSLATION_ERROR_MESSAGE_ATTRIBUTE,
    TRANSLATION_ERROR_TYPE_ATTRIBUTE,
    final_span_attributes,
    final_trace_attributes,
    map_span_start,
    map_trace_start,
    source_span_error_message,
)

logger = logging.getLogger(__name__)

SpanDataT = TypeVar("SpanDataT", bound=SpanData)


@dataclass(slots=True)
class _OpenTelemetryState:
    span: OpenTelemetrySpan
    started_at: str
    context_token: Token[Context] | None = None


class JunjoOpenAIAgentsTraceProvider(OpenAITraceProvider):
    """Delegate OpenAI tracing while mirroring its live hierarchy to OpenTelemetry."""

    def __init__(
        self,
        *,
        original_provider: OpenAITraceProvider,
        tracer_provider: TracerProvider,
    ) -> None:
        self.original_provider = original_provider
        self.tracer_provider = tracer_provider
        self._tracer = tracer_provider.get_tracer("junjo.plugins.openai_agents")
        self._resource_attributes = dict(tracer_provider.resource.attributes)
        self._active_traces: dict[str, _OpenTelemetryState] = {}
        self._active_spans: dict[str, _OpenTelemetryState] = {}
        self._lock = Lock()

    def register_processor(self, processor: TracingProcessor) -> None:
        self.original_provider.register_processor(processor)

    def set_processors(self, processors: list[TracingProcessor]) -> None:
        self.original_provider.set_processors(processors)

    def get_current_trace(self) -> OpenAITrace | None:
        return self.original_provider.get_current_trace()

    def get_current_span(self) -> OpenAISpan[Any] | None:
        return self.original_provider.get_current_span()

    def set_disabled(self, disabled: bool) -> None:
        self.original_provider.set_disabled(disabled)

    def time_iso(self) -> str:
        return self.original_provider.time_iso()

    def gen_trace_id(self) -> str:
        return self.original_provider.gen_trace_id()

    def gen_span_id(self) -> str:
        return self.original_provider.gen_span_id()

    def gen_group_id(self) -> str:
        return self.original_provider.gen_group_id()

    def create_trace(
        self,
        name: str,
        trace_id: str | None = None,
        group_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        disabled: bool = False,
        tracing: TracingConfig | None = None,
    ) -> OpenAITrace:
        source = self.original_provider.create_trace(
            name=name,
            trace_id=trace_id,
            group_id=group_id,
            metadata=metadata,
            disabled=disabled,
            tracing=tracing,
        )
        return _TraceWrapper(source=source, bridge=self)

    def create_span(
        self,
        span_data: SpanDataT,
        span_id: str | None = None,
        parent: OpenAITrace | OpenAISpan[Any] | None = None,
        disabled: bool = False,
    ) -> OpenAISpan[SpanDataT]:
        source = self.original_provider.create_span(
            span_data=span_data,
            span_id=span_id,
            parent=_unwrap_parent(parent),
            disabled=disabled,
        )
        return _SpanWrapper(source=source, bridge=self)

    def force_flush(self) -> None:
        self.original_provider.force_flush()

    def shutdown(self) -> None:
        self.original_provider.shutdown()

    def _start_trace(self, source: OpenAITrace, *, mark_as_current: bool) -> _OpenTelemetryState | None:
        if source.trace_id == "no-op":
            return None
        try:
            mapped = map_trace_start(source)
            started_ns = time_ns()
            span = self._tracer.start_span(
                mapped.name,
                context=otel_context.get_current(),
                kind=SpanKind.INTERNAL,
                attributes=mapped.attributes,
                start_time=started_ns,
            )
            state = _OpenTelemetryState(span=span, started_at=_iso_from_ns(started_ns))
            with self._lock:
                self._active_traces[source.trace_id] = state
            if mark_as_current:
                state.context_token = otel_context.attach(set_span_in_context(span))
            return state
        except Exception as error:
            _log_translation_failure("Unable to start translated OpenAI workflow span", error)
            return None

    def _finish_trace(
        self,
        source: OpenAITrace,
        state: _OpenTelemetryState | None,
        *,
        reset_current: bool,
        exception: BaseException | None,
    ) -> None:
        if state is None:
            return
        ended_ns = time_ns()
        try:
            if state.span.is_recording():
                try:
                    state.span.set_attributes(
                        final_trace_attributes(
                            source,
                            started_at=state.started_at,
                            ended_at=_iso_from_ns(ended_ns),
                        )
                    )
                except Exception as error:
                    _annotate_translation_failure(state.span, error)
                if exception is not None:
                    _record_exception(state.span, exception)
        finally:
            if reset_current:
                _detach_context(state)
            state.span.end(end_time=ended_ns)
            with self._lock:
                self._active_traces.pop(source.trace_id, None)

    def _start_span(
        self,
        source: OpenAISpan[Any],
        *,
        mark_as_current: bool,
    ) -> _OpenTelemetryState | None:
        if source.trace_id == "no-op" or source.span_id == "no-op":
            return None
        try:
            mapped = map_span_start(source)
            started_ns = _iso_to_ns(source.started_at) or time_ns()
            span = self._tracer.start_span(
                mapped.name,
                context=self._parent_context(source),
                kind=SpanKind.INTERNAL,
                attributes=mapped.attributes,
                start_time=started_ns,
            )
            state = _OpenTelemetryState(span=span, started_at=_iso_from_ns(started_ns))
            with self._lock:
                self._active_spans[source.span_id] = state
            if mark_as_current:
                state.context_token = otel_context.attach(set_span_in_context(span))
            return state
        except Exception as error:
            _log_translation_failure("Unable to start translated OpenAI Agents span", error)
            return None

    def _finish_span(
        self,
        source: OpenAISpan[Any],
        state: _OpenTelemetryState | None,
        *,
        reset_current: bool,
        exception: BaseException | None,
    ) -> None:
        if state is None:
            return
        ended_ns = _iso_to_ns(source.ended_at) or time_ns()
        try:
            if state.span.is_recording():
                try:
                    state.span.set_attributes(final_span_attributes(source))
                except Exception as error:
                    _annotate_translation_failure(state.span, error)

                message = source_span_error_message(source)
                if source.error is not None:
                    state.span.set_status(Status(StatusCode.ERROR, message))
                if exception is not None:
                    _record_exception(state.span, exception)

                if isinstance(source.span_data, AgentSpanData):
                    record_openai_agent_evidence(
                        agent_name=source.span_data.name,
                        span_context=state.span.get_span_context(),
                        resource_attributes=self._resource_attributes,
                    )
        finally:
            if reset_current:
                _detach_context(state)
            state.span.end(end_time=ended_ns)
            with self._lock:
                self._active_spans.pop(source.span_id, None)

    def _parent_context(self, source: OpenAISpan[Any]) -> Context:
        with self._lock:
            parent = self._active_spans.get(source.parent_id) if source.parent_id else None
            if parent is None:
                parent = self._active_traces.get(source.trace_id)
        return set_span_in_context(parent.span) if parent is not None else otel_context.get_current()


class _TraceWrapper(OpenAITrace):
    def __init__(self, *, source: OpenAITrace, bridge: JunjoOpenAIAgentsTraceProvider) -> None:
        self._source = source
        self._bridge = bridge
        self._state: _OpenTelemetryState | None = None
        self._started = False
        self._finished = False

    @property
    def trace_id(self) -> str:
        return self._source.trace_id

    @property
    def name(self) -> str:
        return self._source.name

    @property
    def tracing_api_key(self) -> str | None:
        return self._source.tracing_api_key

    @property
    def group_id(self) -> object:
        return getattr(self._source, "group_id", None)

    @property
    def metadata(self) -> object:
        return getattr(self._source, "metadata", None)

    def start(self, mark_as_current: bool = False) -> None:
        self._source.start(mark_as_current=mark_as_current)
        if self._started:
            return
        self._started = True
        self._state = self._bridge._start_trace(self._source, mark_as_current=mark_as_current)

    def finish(self, reset_current: bool = False) -> None:
        self._source.finish(reset_current=reset_current)
        self._finish_otel(reset_current=reset_current, exception=None)

    def __enter__(self) -> OpenAITrace:
        self._source.__enter__()
        if not self._started:
            self._started = True
            self._state = self._bridge._start_trace(self._source, mark_as_current=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._source.__exit__(exc_type, exc_val, exc_tb)
        finally:
            self._finish_otel(reset_current=True, exception=exc_val)

    def export(self) -> dict[str, Any] | None:
        return self._source.export()

    def _finish_otel(self, *, reset_current: bool, exception: BaseException | None) -> None:
        if not self._started or self._finished:
            return
        self._finished = True
        self._bridge._finish_trace(
            self._source,
            self._state,
            reset_current=reset_current,
            exception=exception,
        )


class _SpanWrapper(OpenAISpan[SpanDataT], Generic[SpanDataT]):
    def __init__(
        self,
        *,
        source: OpenAISpan[SpanDataT],
        bridge: JunjoOpenAIAgentsTraceProvider,
    ) -> None:
        self._source = source
        self._bridge = bridge
        self._state: _OpenTelemetryState | None = None
        self._started = False
        self._finished = False

    @property
    def trace_id(self) -> str:
        return self._source.trace_id

    @property
    def span_id(self) -> str:
        return self._source.span_id

    @property
    def span_data(self) -> SpanDataT:
        return self._source.span_data

    @property
    def parent_id(self) -> str | None:
        return self._source.parent_id

    @property
    def error(self) -> SpanError | None:
        return self._source.error

    @property
    def started_at(self) -> str | None:
        return self._source.started_at

    @property
    def ended_at(self) -> str | None:
        return self._source.ended_at

    @property
    def tracing_api_key(self) -> str | None:
        return self._source.tracing_api_key

    @property
    def trace_metadata(self) -> dict[str, Any] | None:
        return self._source.trace_metadata

    def start(self, mark_as_current: bool = False) -> None:
        self._source.start(mark_as_current=mark_as_current)
        if self._started:
            return
        self._started = True
        self._state = self._bridge._start_span(self._source, mark_as_current=mark_as_current)

    def finish(self, reset_current: bool = False) -> None:
        self._source.finish(reset_current=reset_current)
        self._finish_otel(reset_current=reset_current, exception=None)

    def __enter__(self) -> OpenAISpan[SpanDataT]:
        self._source.__enter__()
        if not self._started:
            self._started = True
            self._state = self._bridge._start_span(self._source, mark_as_current=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._source.__exit__(exc_type, exc_val, exc_tb)
        finally:
            self._finish_otel(reset_current=True, exception=exc_val)

    def set_error(self, error: SpanError) -> None:
        self._source.set_error(error)

    def export(self) -> dict[str, Any] | None:
        return self._source.export()

    def _finish_otel(self, *, reset_current: bool, exception: BaseException | None) -> None:
        if not self._started or self._finished:
            return
        self._finished = True
        self._bridge._finish_span(
            self._source,
            self._state,
            reset_current=reset_current,
            exception=exception,
        )


def _unwrap_parent(parent: OpenAITrace | OpenAISpan[Any] | None) -> OpenAITrace | OpenAISpan[Any] | None:
    if isinstance(parent, (_TraceWrapper, _SpanWrapper)):
        return parent._source
    return parent


def _detach_context(state: _OpenTelemetryState) -> None:
    token = state.context_token
    if token is None:
        return
    state.context_token = None
    try:
        otel_context.detach(token)
    except Exception as error:
        _log_translation_failure("Unable to restore OpenTelemetry context", error)


def _record_exception(span: OpenTelemetrySpan, exception: BaseException) -> None:
    try:
        span.record_exception(exception)
        span.set_status(Status(StatusCode.ERROR, _safe_exception_text(exception)))
    except Exception as error:
        _annotate_translation_failure(span, error)


def _annotate_translation_failure(span: OpenTelemetrySpan, error: BaseException) -> None:
    try:
        span.set_attribute(TRANSLATION_ERROR_TYPE_ATTRIBUTE, type(error).__name__)
        span.set_attribute(TRANSLATION_ERROR_MESSAGE_ATTRIBUTE, _safe_exception_text(error))
    except Exception:
        pass
    _log_translation_failure("OpenAI Agents telemetry translation failed", error)


def _safe_exception_text(error: BaseException) -> str:
    try:
        return str(error)
    except Exception:
        return type(error).__name__


def _log_translation_failure(message: str, error: BaseException) -> None:
    try:
        logger.warning("%s: %s", message, type(error).__name__)
    except Exception:
        pass


def _iso_to_ns(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp() * 1_000_000_000)


def _iso_from_ns(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000_000, tz=UTC).isoformat()


__all__ = ["JunjoOpenAIAgentsTraceProvider"]
