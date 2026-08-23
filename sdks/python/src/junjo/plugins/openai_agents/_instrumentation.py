"""Explicit lifecycle for Junjo's first-party OpenAI Agents telemetry bridge."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from types import TracebackType

from agents.tracing import TraceProvider as OpenAITraceProvider
from agents.tracing import get_trace_provider, set_trace_provider
from opentelemetry.sdk.trace import TracerProvider

from ._trace_provider import JunjoOpenAIAgentsTraceProvider


class OpenAIAgentsIntegrationError(RuntimeError):
    """The OpenAI Agents integration cannot be configured truthfully."""


@dataclass(slots=True)
class _SharedIntegration:
    tracer_provider: TracerProvider
    original_provider: OpenAITraceProvider
    bridge_provider: JunjoOpenAIAgentsTraceProvider
    references: int = 1


_LOCK = Lock()
_ACTIVE_INTEGRATION: _SharedIntegration | None = None


class OpenAIAgentsIntegration:
    """Closeable ownership handle for the process-level integration.

    Handles returned for the same active OpenTelemetry provider share one
    OpenAI TraceProvider wrapper. Closing the final handle restores the exact
    original OpenAI provider. The integration never shuts down the
    application-owned OpenTelemetry provider or its exporters.
    """

    def __init__(self, shared: _SharedIntegration) -> None:
        self._shared = shared
        self._closed = False

    def close(self) -> None:
        """Release this handle and restore the original OpenAI provider.

        The operation is idempotent. Applications must stop creating Agent
        runs before closing the final process-lifetime handle.
        """

        global _ACTIVE_INTEGRATION
        with _LOCK:
            if self._closed:
                return
            self._closed = True
            self._shared.references -= 1
            if self._shared.references != 0:
                return
            set_trace_provider(self._shared.original_provider)
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


def instrument_openai_agents(*, tracer_provider: TracerProvider) -> OpenAIAgentsIntegration:
    """Translate first-party OpenAI Agents traces into OpenTelemetry spans.

    The application owns the supplied provider, processors, exporters,
    resource identity, and shutdown order. This function explicitly wraps the
    active OpenAI Agents ``TraceProvider`` while preserving its configured
    processors and native trace-export policy. Importing the module has no
    instrumentation side effect.

    Repeated calls with the same active OpenTelemetry provider share one
    registration and return independently closeable handles. A different
    provider cannot be selected until the active integration is closed.

    :param tracer_provider: Process-lifetime OpenTelemetry SDK provider that
        owns the application's existing trace pipeline.
    :return: Ownership handle that must be closed before the provider shuts
        down.
    :raises TypeError: If ``tracer_provider`` is not an SDK provider.
    :raises OpenAIAgentsIntegrationError: If another provider is already
        active for the process-level OpenAI integration.
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

        original_provider = get_trace_provider()
        bridge_provider = JunjoOpenAIAgentsTraceProvider(
            original_provider=original_provider,
            tracer_provider=tracer_provider,
        )
        set_trace_provider(bridge_provider)
        shared = _SharedIntegration(
            tracer_provider=tracer_provider,
            original_provider=original_provider,
            bridge_provider=bridge_provider,
        )
        _ACTIVE_INTEGRATION = shared
        return OpenAIAgentsIntegration(shared)


__all__ = [
    "OpenAIAgentsIntegration",
    "OpenAIAgentsIntegrationError",
    "instrument_openai_agents",
]
