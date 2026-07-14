"""Lifespan-owned optional Junjo AI Studio telemetry configuration."""

from dataclasses import dataclass
from typing import Protocol

from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from opentelemetry import metrics, trace
from opentelemetry.metrics import _internal as metrics_internal
from opentelemetry.sdk.metrics import MeterProvider
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
    meter_provider: _TelemetryProvider

    def shutdown(self) -> None:
        errors: list[BaseException] = []
        steps = (
            ("trace force flush", self.trace_provider.force_flush),
            ("metric force flush", self.meter_provider.force_flush),
            ("trace shutdown", self.trace_provider.shutdown),
            ("metric shutdown", self.meter_provider.shutdown),
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


def _require_unowned_global_provider_slots() -> None:
    """Fail before exporter workers exist when this process already owns OTel.

    OpenTelemetry exposes setters but no public ownership preflight. The SDK's
    set-once guards are the authoritative process-global slots used by those
    setters, so this small adapter contains the unavoidable private API touch.
    """

    if (
        trace._TRACER_PROVIDER_SET_ONCE._done  # pyright: ignore[reportPrivateUsage]
        or metrics_internal._METER_PROVIDER_SET_ONCE._done  # pyright: ignore[reportPrivateUsage]
    ):
        raise RuntimeError("OpenTelemetry providers are already installed")


def start_telemetry(settings: TelemetrySettings) -> TelemetryRuntime:
    _require_unowned_global_provider_slots()
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
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[exporter.metric_reader],
    )
    runtime = TelemetryRuntime(
        trace_provider=trace_provider,
        meter_provider=meter_provider,
    )

    trace.set_tracer_provider(trace_provider)
    metrics.set_meter_provider(meter_provider)
    if trace.get_tracer_provider() is not trace_provider or metrics.get_meter_provider() is not meter_provider:
        try:
            runtime.shutdown()
        except BaseException as cleanup_error:
            raise BaseExceptionGroup(
                "telemetry provider installation and cleanup both failed",
                [
                    RuntimeError("OpenTelemetry providers are already installed"),
                    cleanup_error,
                ],
            ) from None
        raise RuntimeError("OpenTelemetry providers are already installed")

    return runtime
