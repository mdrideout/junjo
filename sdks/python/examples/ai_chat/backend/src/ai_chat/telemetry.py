"""Lifespan-owned optional Junjo AI Studio telemetry configuration."""

from dataclasses import dataclass
from typing import Protocol

from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from ai_chat import __version__
from ai_chat.config import (
    STUDIO_SERVICE_NAME,
    STUDIO_SERVICE_NAMESPACE,
    TelemetrySettings,
)


class _TelemetryProvider(Protocol):
    def force_flush(self) -> object: ...

    def shutdown(self) -> object: ...


@dataclass(slots=True)
class TelemetryRuntime:
    """The exact provider lifetime installed for one application lifespan."""

    trace_provider: _TelemetryProvider

    def shutdown(self) -> None:
        errors: list[BaseException] = []
        steps = (
            ("trace force flush", self.trace_provider.force_flush),
            ("trace shutdown", self.trace_provider.shutdown),
        )
        for label, step in steps:
            try:
                result = step()
                if result is False:
                    errors.append(RuntimeError(f"telemetry {label} timed out"))
            except BaseException as error:
                errors.append(error)

        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise BaseExceptionGroup("telemetry cleanup failed", errors)


def _require_unowned_global_trace_provider_slot() -> None:
    """Fail before an exporter worker exists when this process already owns tracing.

    OpenTelemetry exposes setters but no public ownership preflight. The SDK's
    set-once guard is the authoritative process-global slot used by the trace
    setter, so this small adapter contains the unavoidable private API touch.
    """

    if trace._TRACER_PROVIDER_SET_ONCE._done:  # pyright: ignore[reportPrivateUsage]
        raise RuntimeError("OpenTelemetry tracer provider is already installed")


def start_telemetry(settings: TelemetrySettings) -> TelemetryRuntime:
    _require_unowned_global_trace_provider_slot()
    resource = Resource.create(
        {
            "service.namespace": STUDIO_SERVICE_NAMESPACE,
            "service.name": STUDIO_SERVICE_NAME,
            "service.version": __version__,
        }
    )
    exporter = JunjoOtelExporter(
        host=settings.host,
        port=str(settings.port),
        api_key=settings.api_key,
        insecure=settings.insecure,
    )
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(exporter.span_processor)
    runtime = TelemetryRuntime(trace_provider=trace_provider)

    trace.set_tracer_provider(trace_provider)
    if trace.get_tracer_provider() is not trace_provider:
        try:
            runtime.shutdown()
        except BaseException as cleanup_error:
            raise BaseExceptionGroup(
                "telemetry provider installation and cleanup both failed",
                [
                    RuntimeError("OpenTelemetry tracer provider is already installed"),
                    cleanup_error,
                ],
            ) from None
        raise RuntimeError("OpenTelemetry tracer provider is already installed")

    GoogleGenAIInstrumentor().instrument(tracer_provider=trace_provider)

    return runtime
