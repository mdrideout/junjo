from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


class OpenTelemetryHooks:
    """
    A class that provides OpenTelemetry hooks for Junjo workflows.
    """

    def __init__(self, service_name: str, jaeger_host: str, jaeger_port: int):
        """Initializes the OpenTelemetry hooks."""

        resource = Resource(attributes={
            SERVICE_NAME: "test_service_name"
        })

        tracerProvider = TracerProvider(resource=resource)

        otlpProcessor = BatchSpanProcessor(OTLPSpanExporter(endpoint="localhost:4317"))
        tracerProvider.add_span_processor(otlpProcessor)

        consoleProcessor = BatchSpanProcessor(ConsoleSpanExporter())
        tracerProvider.add_span_processor(consoleProcessor)

        trace.set_tracer_provider(tracerProvider)

        readerOtlp = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint="localhost:4317")
        )
        readerConsole = PeriodicExportingMetricReader(ConsoleMetricExporter())

        meterProvider = MeterProvider(resource=resource, metric_readers=[readerOtlp, readerConsole])
        metrics.set_meter_provider(meterProvider)


    def before_workflow_execute(self, workflow_id: str):
        pass


    def after_workflow_execute(self, workflow_id: str, state: dict, duration: float):
        pass


    def before_node_execute(self, node_id: str, state: dict):
        pass


    def after_node_execute(self, node_id: str, state: dict, duration: float):
        pass
