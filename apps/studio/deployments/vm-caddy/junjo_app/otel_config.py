import os
import textwrap

from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
from loguru import logger
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def _render_warning_box(title: str, lines: list[str], width: int = 62) -> str:
    """Render a consistently sized Unicode warning box with wrapped content."""
    top = "╔" + ("═" * (width + 2)) + "╗"
    sep = "╠" + ("═" * (width + 2)) + "╣"
    bottom = "╚" + ("═" * (width + 2)) + "╝"

    def row(text: str = "") -> str:
        return f"║ {text.ljust(width)} ║"

    out: list[str] = [top, row(title), sep, row()]
    for line in lines:
        wrapped = textwrap.wrap(line, width=width) or [""]
        for part in wrapped:
            out.append(row(part))
    out.append(row())
    out.append(bottom)
    return "\n".join(out)


def setup_telemetry() -> tuple[TracerProvider, MeterProvider] | None:
    """Set up OpenTelemetry providers for the deployment example."""

    # Load the JUNJO_AI_STUDIO_API_KEY from the environment variable
    JUNJO_AI_STUDIO_API_KEY = os.getenv("JUNJO_AI_STUDIO_API_KEY")

    if (
        not JUNJO_AI_STUDIO_API_KEY
        or JUNJO_AI_STUDIO_API_KEY == "junjo_ai_studio_api_key_here"
    ):
        warning_box = _render_warning_box(
            title="🚨 Example App 'junjo_app' API KEY 🔑 Required",
            lines=[
                "This deployment example contains a 'junjo_app' example application in the project root.",
                "This warning applies to that example container only.",
                "",
                "1. Go to Junjo AI Studio UI: http://localhost:26153",
                "2. Create an API key from the API Keys page",
                "3. In the root .env file, set: JUNJO_AI_STUDIO_API_KEY=<key>",
                "4. Recreate only the example app container:",
                "   docker compose up --force-recreate --no-deps junjo-app -d",
            ],
        )

        logger.error(f"\n{warning_box}\n")
        return False

    # Configure OpenTelemetry for this application
    # Create the OpenTelemetry Resource to identify this service
    resource = Resource.create({"service.name": "Junjo Deployment Example"})

    # Set up tracing for this application
    tracer_provider = TracerProvider(resource=resource)

    # Construct a Junjo exporter for Junjo AI Studio (see docker-compose.yml)
    junjo_ai_studio_exporter = JunjoOtelExporter(
        # The Junjo AI Studio service name on the same Compose network
        host="junjo-ai-studio-ingestion",  # Junjo AI Studio ingestion on the shared Docker network
        port="26155",
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

    return tracer_provider, meter_provider
