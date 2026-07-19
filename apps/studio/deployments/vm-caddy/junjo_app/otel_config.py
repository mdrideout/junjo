import os
import textwrap

from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


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


def setup_telemetry() -> TracerProvider | None:
    """Set up OpenTelemetry trace export for the deployment example."""

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
        return None

    # Configure OpenTelemetry for this application
    # Create the OpenTelemetry Resource to identify this service
    resource = Resource.create({"service.name": "Junjo Deployment Example"})

    # Set up tracing for this application
    tracer_provider = TracerProvider(resource=resource)

    # Export standard OTLP traces to Studio (see docker-compose.yml).
    studio_trace_exporter = OTLPSpanExporter(
        endpoint="junjo-ai-studio-ingestion:26155",
        insecure=True,
        headers=(("x-junjo-api-key", JUNJO_AI_STUDIO_API_KEY),),
        timeout=120,
    )

    tracer_provider.add_span_processor(BatchSpanProcessor(studio_trace_exporter))
    trace.set_tracer_provider(tracer_provider)

    return tracer_provider
