import os

from junjo.telemetry.junjo_server_otel_exporter import JunjoServerOtelExporter
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def init_otel(service_name: str):
    """Configure OpenTelemetry for this application."""

    # Load the JUNJO_SERVER_API_KEY from the environment variable
    JUNJO_SERVER_API_KEY = os.getenv("JUNJO_SERVER_API_KEY")
    if JUNJO_SERVER_API_KEY is None:
        print("JUNJO_SERVER_API_KEY environment variable is not set. "
                         "Generate a new API key in the Junjo Server UI.")
        return

    # Configure OpenTelemetry for this application
    # Create the OpenTelemetry Resource to identify this service
    resource = Resource.create({"service.name": service_name})

    # Set up tracing for this application
    tracer_provider = TracerProvider(resource=resource)

    # Construct a Junjo exporter for Junjo Server (see junjo-server docker-compose.yml)
    junjo_server_exporter = JunjoServerOtelExporter(
        host="localhost",
        port="50051",
        api_key=JUNJO_SERVER_API_KEY,
        insecure=True,
    )

    # Set up span processors
    # Add the Junjo span processor (Junjo Server and Jaeger)
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
