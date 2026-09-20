"""Shared initialization for the application and diagnostic runs."""

import os

from openinference.instrumentation.openai import OpenAIInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter


def init_telemetry() -> TracerProvider:
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.namespace": "junjo.examples",
                "service.name": "junjo_openai_sdk",
            }
        )
    )
    exporter = JunjoOtelExporter(
        endpoint=os.environ["JUNJO_OTLP_ENDPOINT"],
        api_key=os.environ["JUNJO_AI_STUDIO_API_KEY"],
        insecure=os.environ.get("JUNJO_OTLP_INSECURE", "false").lower() == "true",
    )
    provider.add_span_processor(exporter.span_processor)
    trace.set_tracer_provider(provider)
    OpenAIInstrumentor().instrument(tracer_provider=provider)
    return provider
