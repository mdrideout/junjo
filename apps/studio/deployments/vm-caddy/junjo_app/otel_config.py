import os

from junjo.telemetry.junjo_server_otel_exporter import JunjoServerOtelExporter

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

def setup_telemetry():
    """
    Sets up the OpenTelemetry tracer and exporter.
    """
    
    # Load the JUNJO_SERVER_API_KEY from the environment variable
    JUNJO_SERVER_API_KEY = os.getenv("JUNJO_SERVER_API_KEY")
    if JUNJO_SERVER_API_KEY is None:
        print("JUNJO_SERVER_API_KEY environment variable is not set. "
                         "Generate a new API key in the Junjo Server UI.")
        return

    # Configure OpenTelemetry for this application
    # Create the OpenTelemetry Resource to identify this service
    resource = Resource.create({"service.name": "Junjo Deployment Example"})

    # Set up tracing for this application
    tracer_provider = TracerProvider(resource=resource)

    # Construct a Junjo exporter for Junjo Server (see junjo-server docker-compose.yml)
    junjo_server_exporter = JunjoServerOtelExporter(
        host="junjo-server-ingestion",
        port="50051",
        api_key=JUNJO_SERVER_API_KEY,
        insecure=True,
    )

    # Set up span processors
    # Add the Junjo span processor
    # Add more span processors if desired
    tracer_provider.add_span_processor(junjo_server_exporter.span_processor)
    trace.set_tracer_provider(tracer_provider)

    return