import os

from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def init_otel(service_name: str) -> JunjoOtelExporter | None:
    """Configure OpenTelemetry for this application."""

    # Load the JUNJO_AI_STUDIO_API_KEY from the environment variable
    JUNJO_AI_STUDIO_API_KEY = os.getenv("JUNJO_AI_STUDIO_API_KEY")
    if JUNJO_AI_STUDIO_API_KEY is None:
        print("JUNJO_AI_STUDIO_API_KEY environment variable is not set. "
                         "Generate a new API key in the Junjo AI Studio UI.")
        return None

    # Configure OpenTelemetry for this application
    # Create the OpenTelemetry Resource to identify this service
    resource = Resource.create({"service.name": service_name})

    # Set up tracing for this application
    tracer_provider = TracerProvider(resource=resource)

    # Construct a Junjo exporter for Junjo AI Studio
    # This example is configured for a local instance of Junjo AI Studio
    # See https://github.com/mdrideout/junjo-ai-studio-minimal-build
    junjo_ai_studio_exporter = JunjoOtelExporter(
        host="localhost",
        port="50051",
        api_key=JUNJO_AI_STUDIO_API_KEY,
        insecure=True,
    )

    # Set up span processors
    # Add the Junjo span processor
    # Add more span processors if desired
    tracer_provider.add_span_processor(junjo_ai_studio_exporter.span_processor)
    trace.set_tracer_provider(tracer_provider)

    # Set up metrics
    #    - Construct with the Junjo metric reader
    #    - Add more metric readers if desired
    junjo_metric_reader = junjo_ai_studio_exporter.metric_reader
    meter_provider = MeterProvider(
        resource=resource, metric_readers=[junjo_metric_reader]
    )
    metrics.set_meter_provider(meter_provider)

    # Instrument OpenInference Libraries
    # Google genai
    GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)

    return junjo_ai_studio_exporter
