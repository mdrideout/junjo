from contextlib import AbstractContextManager

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span


# --- OpenTelemetry Provider ---
class OpenTelemetryProvider:
    """Provides OpenTelemetry tracing and metrics configuration and utilities."""

    def __init__(self, service_name: str, host: str, port: str):
        """Initializes the OpenTelemetry hooks."""

        # TEMPORARY
        host = "localhost"
        port = "4317"


        resource = Resource(attributes={
            SERVICE_NAME: service_name
        })

        tracer_provider = TracerProvider(resource=resource)

        otlpProcessor = BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{host}:{port}", insecure=True))
        tracer_provider.add_span_processor(otlpProcessor)

        consoleProcessor = BatchSpanProcessor(ConsoleSpanExporter())
        tracer_provider.add_span_processor(consoleProcessor)
        trace.set_tracer_provider(tracer_provider)

        # Make the tracer accessible
        self._tracer = trace.get_tracer(__name__)

        readerOtlp = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{host}:{port}", insecure=True)
        )
        readerConsole = PeriodicExportingMetricReader(ConsoleMetricExporter())
        meterProvider = MeterProvider(resource=resource, metric_readers=[readerConsole, readerOtlp])
        metrics.set_meter_provider(meterProvider)

        # Make the metrics accessible
        self._meter = metrics.get_meter(__name__)

        # Local dictionaries to track spans and tokens so we can close them in the “after” hooks
        self._workflow_spans: dict[str, tuple[Span, AbstractContextManager]] = {}
        self._node_spans: dict[str, tuple[Span, AbstractContextManager]] = {}

    def get_tracer(self):
        """Gets the configured tracer."""
        return self._tracer

    def get_meter(self):
        return self._meter
