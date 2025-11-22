import os
import time

from junjo.telemetry.junjo_server_otel_exporter import JunjoServerOtelExporter
from loguru import logger

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def setup_telemetry():
    """
    Sets up the OpenTelemetry tracer and exporter.
    Returns:
        bool: True if setup was successful, False otherwise.
    """

    # Load the JUNJO_AI_STUDIO_API_KEY from the environment variable
    JUNJO_AI_STUDIO_API_KEY = os.getenv("JUNJO_AI_STUDIO_API_KEY")

    if (
        not JUNJO_AI_STUDIO_API_KEY
        or JUNJO_AI_STUDIO_API_KEY == "junjo_ai_studio_api_key_here"
    ):
        time.sleep(4)

        logger.error(
            "\n"
            "╔════════════════════════════════════════════════════════════════════════════╗\n"
            "║ 🚨 API KEY 🔑 CONFIGURATION REQUIRED                                       ║\n"
            "╠════════════════════════════════════════════════════════════════════════════╣\n"
            "║                                                                            ║\n"
            "║  The Junjo App requires a valid API Key to send telemetry.                 ║\n"
            "║                                                                            ║\n"
            "║  1. Go to your Junjo AI Studio UI: http://localhost:5153                   ║\n"
            "║  2. Create a new API Key in the Settings                                   ║\n"
            "║  3. Open your .env file                                                    ║\n"
            "║  4. Set JUNJO_AI_STUDIO_API_KEY=<your-new-key>                             ║\n"
            "║  5. Apply changes: docker compose up -d junjo-app                          ║\n"
            "║     - The junjo-app container must rebuild to pickup .env changes          ║\n"
            "║                                                                            ║\n"
            "╚════════════════════════════════════════════════════════════════════════════╝\n"
        )
        return False

    # Configure OpenTelemetry for this application
    # Create the OpenTelemetry Resource to identify this service
    resource = Resource.create({"service.name": "Junjo Deployment Example"})

    # Set up tracing for this application
    tracer_provider = TracerProvider(resource=resource)

    # Construct a Junjo exporter for Junjo Server (see docker-compose.yml)
    # Uses insecure docker compose instance host references because it's on the same docker network
    junjo_server_exporter = JunjoServerOtelExporter(
        host="junjo-ai-studio-ingestion",
        port="50051",
        api_key=JUNJO_AI_STUDIO_API_KEY,
        insecure=True,
    )

    # Set up span processors
    # Add the Junjo span processor
    # Add more span processors if desired
    tracer_provider.add_span_processor(junjo_server_exporter.span_processor)
    trace.set_tracer_provider(tracer_provider)

    # Set up metrics
    #    - Construct with the Junjo metric reader (Junjo Server and Jaeger)
    #    - Add more metric readers if desired
    junjo_server_metric_reader = junjo_server_exporter.metric_reader
    meter_provider = MeterProvider(
        resource=resource, metric_readers=[junjo_server_metric_reader]
    )
    metrics.set_meter_provider(meter_provider)

    return True
