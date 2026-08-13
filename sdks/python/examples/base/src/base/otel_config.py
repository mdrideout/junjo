import logging
import os

from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger(__name__)


def _environment_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{name} must be true or false.")


def init_otel(
    service_name: str,
) -> TracerProvider | None:
    """Configure OpenTelemetry trace export and return the owning provider."""

    # Load the JUNJO_AI_STUDIO_API_KEY from the environment variable
    JUNJO_AI_STUDIO_API_KEY = os.getenv("JUNJO_AI_STUDIO_API_KEY")
    if JUNJO_AI_STUDIO_API_KEY is None:
        logger.warning(
            "JUNJO_AI_STUDIO_API_KEY environment variable is not set. Generate a new API key in the Junjo AI Studio UI."
        )
        return None

    # Configure OpenTelemetry for this application
    # Create the OpenTelemetry Resource to identify this service
    resource = Resource.create({"service.name": service_name})

    # Set up tracing for this application
    tracer_provider = TracerProvider(resource=resource)

    # Construct a Junjo exporter for Junjo AI Studio
    # This example runs directly on the local machine.
    # See https://github.com/mdrideout/junjo-ai-studio-minimal-build
    junjo_ai_studio_exporter = JunjoOtelExporter(
        endpoint=os.getenv("JUNJO_AI_STUDIO_OTLP_ENDPOINT", "localhost:26155"),
        api_key=JUNJO_AI_STUDIO_API_KEY,
        insecure=_environment_bool("JUNJO_AI_STUDIO_OTLP_INSECURE", default=True),
    )

    # Set up span processors
    # Add the Junjo span processor
    # Add more span processors if desired
    tracer_provider.add_span_processor(junjo_ai_studio_exporter.span_processor)
    trace.set_tracer_provider(tracer_provider)

    # Instrument OpenInference Libraries
    # Google genai
    GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)

    return tracer_provider
