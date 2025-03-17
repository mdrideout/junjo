from junjo.telemetry.junjo_server_otel_exporter import JunjoServerOtelExporter
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def init_otel():
    """Configure OpenTelemetry for this application."""

    # Configure OpenTelemetry for this application
    # Create the OpenTelemetry Resource to identify this service
    resource = Resource.create({"service.name": "Junjo Chat App"})

    # Set up tracing for this application
    tracer_provider = TracerProvider(resource=resource)

    # Construct a Junjo exporter for Jaeger (see junjo-server docker-compose.yml)
    junjo_jaeger_exporter = JunjoServerOtelExporter(
        host="localhost",
        port="4317",
        insecure=True,
    )

    # Construct a Junjo exporter for Junjo Server (see junjo-server docker-compose.yml)
    junjo_server_exporter = JunjoServerOtelExporter(
        host="localhost",
        port="50051",
        insecure=True,
    )

    # Set up span processors
    # Add the Junjo span processor (Junjo Server and Jaeger)
    # Add more span processors if desired
    tracer_provider.add_span_processor(junjo_jaeger_exporter.span_processor)
    tracer_provider.add_span_processor(junjo_server_exporter.span_processor)
    trace.set_tracer_provider(tracer_provider)

    # Set up metrics
    #    - Construct with the Junjo metric reader (Junjo Server and Jaeger)
    #    - Add more metric readers if desired
    junjo_jaeger_metric_reader = junjo_jaeger_exporter.metric_reader
    junjo_server_metric_reader = junjo_server_exporter.metric_reader
    meter_provider = MeterProvider(
        resource=resource, metric_readers=[junjo_jaeger_metric_reader, junjo_server_metric_reader]
    )
    metrics.set_meter_provider(meter_provider)
