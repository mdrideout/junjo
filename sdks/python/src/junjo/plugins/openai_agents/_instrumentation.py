"""Explicit OpenAI Agents OpenTelemetry instrumentation lifecycle."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from threading import Lock
from types import TracebackType
from weakref import WeakKeyDictionary

from opentelemetry.instrumentation.genai.openai import OpenAIInstrumentor
from opentelemetry.instrumentation.genai.openai_agents import OpenAIAgentsInstrumentor
from opentelemetry.sdk.trace import ReadableSpan, Span, TracerProvider
from opentelemetry.sdk.trace.export import SpanProcessor

from ...studio import OpenTelemetrySpanReference


class OpenAIAgentsIntegrationError(RuntimeError):
    """The OpenAI Agents integration cannot be configured truthfully."""


@dataclass(slots=True)
class _Capture:
    expected_agent_name: str
    evidence: list[OpenTelemetrySpanReference] = field(default_factory=list)


_ACTIVE_CAPTURE: ContextVar[_Capture | None] = ContextVar(
    "junjo_openai_agent_evidence_capture",
    default=None,
)


class _EvidenceObserver(SpanProcessor):
    """Observe completed standard Agent spans without mutating or exporting them."""

    def __init__(self) -> None:
        self._enabled = True

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def on_start(self, span: Span, parent_context: object | None = None) -> None:
        del span, parent_context

    def on_end(self, span: ReadableSpan) -> None:
        capture = _ACTIVE_CAPTURE.get()
        if not self._enabled or capture is None:
            return
        attributes = span.attributes or {}
        if attributes.get("gen_ai.operation.name") != "invoke_agent":
            return
        if attributes.get("gen_ai.agent.name") != capture.expected_agent_name:
            return
        service_name = span.resource.attributes.get("service.name")
        if not isinstance(service_name, str) or not service_name:
            return
        service_namespace = span.resource.attributes.get("service.namespace", "")
        if not isinstance(service_namespace, str):
            service_namespace = ""
        context = span.context
        if context is None or not context.is_valid:
            return
        capture.evidence.append(
            OpenTelemetrySpanReference(
                service_namespace=service_namespace,
                service_name=service_name,
                trace_id=format(context.trace_id, "032x"),
                span_id=format(context.span_id, "016x"),
            )
        )

    def shutdown(self) -> None:
        self.disable()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        del timeout_millis
        return True


@dataclass(slots=True)
class _SharedIntegration:
    tracer_provider: TracerProvider
    observer: _EvidenceObserver
    agent_instrumentor: OpenAIAgentsInstrumentor
    client_instrumentor: OpenAIInstrumentor
    owns_agent_instrumentation: bool
    owns_client_instrumentation: bool
    references: int = 1


_LOCK = Lock()
_ACTIVE_INTEGRATION: _SharedIntegration | None = None
_OBSERVERS: WeakKeyDictionary[TracerProvider, _EvidenceObserver] = WeakKeyDictionary()


class OpenAIAgentsIntegration:
    """Closeable ownership handle for the process-level integration.

    Handles returned for the same active provider share one instrumentation
    registration. Closing a handle releases only that reference. The last
    handle removes only instrumentation installed by Junjo; it never shuts
    down the application-owned tracer provider or its exporters.
    """

    def __init__(self, shared: _SharedIntegration) -> None:
        self._shared = shared
        self._closed = False

    def close(self) -> None:
        """Release this handle and undo instrumentation Junjo installed.

        The operation is idempotent. Pre-existing OpenAI Agents or OpenAI
        client instrumentation remains active because Junjo did not own it.
        """

        global _ACTIVE_INTEGRATION
        with _LOCK:
            if self._closed:
                return
            self._closed = True
            self._shared.references -= 1
            if self._shared.references != 0:
                return
            self._shared.observer.disable()
            if self._shared.owns_client_instrumentation:
                self._shared.client_instrumentor.uninstrument()
            if self._shared.owns_agent_instrumentation:
                self._shared.agent_instrumentor.uninstrument()
            _ACTIVE_INTEGRATION = None

    def __enter__(self) -> OpenAIAgentsIntegration:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()


def instrument_openai_agents(
    *,
    tracer_provider: TracerProvider,
    disable_openai_trace_export: bool = False,
) -> OpenAIAgentsIntegration:
    """Emit standard OpenTelemetry GenAI spans from an OpenAI Agents runtime.

    This explicitly installs the official OpenTelemetry instrumentors for the
    OpenAI Agents SDK and the OpenAI Python client. The application retains
    ownership of the supplied provider, processors, exporters, service
    resource, and shutdown order. Importing this module has no instrumentation
    side effect.

    Repeated calls with the same active provider share one registration and
    return independently closeable handles. A different provider cannot be
    selected while the integration is active. Existing instrumentation is
    preserved rather than installed twice.

    :param tracer_provider: Process-lifetime OpenTelemetry SDK provider that
        owns the application's trace pipeline.
    :param disable_openai_trace_export: Remove the OpenAI Agents SDK's native
        hosted trace processor while this Junjo-owned registration is active.
        This cannot change a pre-existing Agent instrumentation policy.
    :return: Ownership handle that must be closed before the provider shuts
        down.
    :raises TypeError: If ``tracer_provider`` is not an SDK provider.
    :raises OpenAIAgentsIntegrationError: If active instrumentation cannot be
        configured truthfully with the requested provider or native-export
        policy.
    """

    global _ACTIVE_INTEGRATION
    if not isinstance(tracer_provider, TracerProvider):
        raise TypeError("tracer_provider must be an OpenTelemetry SDK TracerProvider.")
    with _LOCK:
        if _ACTIVE_INTEGRATION is not None:
            if _ACTIVE_INTEGRATION.tracer_provider is not tracer_provider:
                raise OpenAIAgentsIntegrationError(
                    "OpenAI Agents is already integrated with a different tracer provider."
                )
            _ACTIVE_INTEGRATION.references += 1
            return OpenAIAgentsIntegration(_ACTIVE_INTEGRATION)

        observer = _OBSERVERS.get(tracer_provider)
        if observer is None:
            observer = _EvidenceObserver()
            tracer_provider.add_span_processor(observer)
            _OBSERVERS[tracer_provider] = observer
        else:
            observer.enable()

        agent_instrumentor = OpenAIAgentsInstrumentor()
        client_instrumentor = OpenAIInstrumentor()
        owns_agent = not agent_instrumentor.is_instrumented_by_opentelemetry
        owns_client = not client_instrumentor.is_instrumented_by_opentelemetry
        if not owns_agent and disable_openai_trace_export:
            observer.disable()
            raise OpenAIAgentsIntegrationError(
                "Cannot change OpenAI native trace export after Agent instrumentation is active."
            )
        _install_instrumentation(
            tracer_provider=tracer_provider,
            disable_openai_trace_export=disable_openai_trace_export,
            observer=observer,
            agent_instrumentor=agent_instrumentor,
            client_instrumentor=client_instrumentor,
            owns_agent=owns_agent,
            owns_client=owns_client,
        )

        shared = _SharedIntegration(
            tracer_provider=tracer_provider,
            observer=observer,
            agent_instrumentor=agent_instrumentor,
            client_instrumentor=client_instrumentor,
            owns_agent_instrumentation=owns_agent,
            owns_client_instrumentation=owns_client,
        )
        _ACTIVE_INTEGRATION = shared
        return OpenAIAgentsIntegration(shared)


def _install_instrumentation(
    *,
    tracer_provider: TracerProvider,
    disable_openai_trace_export: bool,
    observer: _EvidenceObserver,
    agent_instrumentor: OpenAIAgentsInstrumentor,
    client_instrumentor: OpenAIInstrumentor,
    owns_agent: bool,
    owns_client: bool,
) -> None:
    try:
        if owns_agent:
            agent_instrumentor.instrument(
                tracer_provider=tracer_provider,
                disable_openai_trace_export=disable_openai_trace_export,
            )
        if owns_client:
            client_instrumentor.instrument(tracer_provider=tracer_provider)
    except BaseException:
        if owns_client and client_instrumentor.is_instrumented_by_opentelemetry:
            client_instrumentor.uninstrument()
        if owns_agent and agent_instrumentor.is_instrumented_by_opentelemetry:
            agent_instrumentor.uninstrument()
        observer.disable()
        raise


@contextmanager
def capture_openai_agent_evidence(expected_agent_name: str) -> Iterator[_Capture]:
    """Capture one exact standard ``invoke_agent`` span in the current task."""

    capture = _Capture(expected_agent_name=expected_agent_name)
    token: Token[_Capture | None] = _ACTIVE_CAPTURE.set(capture)
    try:
        yield capture
    finally:
        _ACTIVE_CAPTURE.reset(token)
