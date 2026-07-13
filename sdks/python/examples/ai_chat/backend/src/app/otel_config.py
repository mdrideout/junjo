import os

from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def init_otel(service_name: str) -> tuple[TracerProvider, MeterProvider]:
    """Configure OpenTelemetry for this application."""

    # Load the Junjo API key from the environment variable.
    junjo_api_key = os.getenv("JUNJO_AI_STUDIO_API_KEY")
    if junjo_api_key is None:
        raise ValueError("JUNJO_AI_STUDIO_API_KEY environment variable is not set.")

    # Configure OpenTelemetry for this application
    # Create the OpenTelemetry Resource to identify this service
    resource = Resource.create({"service.name": service_name})

    # Set up tracing for this application
    tracer_provider = TracerProvider(resource=resource)

    # Instrument Google GenAI
    GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)

    junjo_ai_studio_exporter = JunjoOtelExporter(
        # AI Chat runs directly on your local machine. Junjo AI Studio ingestion
        # is exposed by its Docker Compose stack on localhost:26155.
        host="localhost",
        port="26155",
        api_key=junjo_api_key,
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
    meter_provider = MeterProvider(resource=resource, metric_readers=[junjo_metric_reader])
    metrics.set_meter_provider(meter_provider)

    return tracer_provider, meter_provider
