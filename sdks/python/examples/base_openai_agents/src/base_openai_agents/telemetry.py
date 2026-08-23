"""Application-owned telemetry runtime for local example and evaluation runs."""

from __future__ import annotations

import os
from dataclasses import dataclass

from junjo.plugins.openai_agents import OpenAIAgentsIntegration, instrument_openai_agents
from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

SERVICE_NAMESPACE = "junjo.examples"
SERVICE_NAME = "base-openai-agents"


@dataclass(slots=True)
class TelemetryRuntime:
    provider: TracerProvider
    integration: OpenAIAgentsIntegration

    def close(self) -> None:
        self.integration.close()
        self.provider.shutdown()


def start_telemetry() -> TelemetryRuntime:
    """Start one process-lifetime provider and optional Studio exporter."""

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.namespace": SERVICE_NAMESPACE,
                "service.name": SERVICE_NAME,
            }
        )
    )
    api_key = os.getenv("JUNJO_AI_STUDIO_API_KEY")
    if api_key:
        exporter = JunjoOtelExporter(
            endpoint=os.getenv("JUNJO_AI_STUDIO_OTLP_ENDPOINT", "localhost:26155"),
            api_key=api_key,
            insecure=_environment_bool("JUNJO_AI_STUDIO_OTLP_INSECURE", default=True),
        )
        provider.add_span_processor(exporter.span_processor)
    trace.set_tracer_provider(provider)
    integration = instrument_openai_agents(
        tracer_provider=provider,
        disable_openai_trace_export=True,
    )
    return TelemetryRuntime(provider=provider, integration=integration)


def _environment_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{name} must be true or false.")
