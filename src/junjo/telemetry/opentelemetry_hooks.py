
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

from junjo.telemetry.hook_schema import (
    SpanCloseSchemaWorkflow,
    SpanOpenSchemaWorkflow,
)


class OpenTelemetryHooks:
    """
    A class that provides OpenTelemetry hooks for Junjo workflows.
    """

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

        # Make the tracer accessible to the hooks
        self._tracer = trace.get_tracer(__name__)

        readerOtlp = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{host}:{port}", insecure=True)
        )
        readerConsole = PeriodicExportingMetricReader(ConsoleMetricExporter())
        meterProvider = MeterProvider(resource=resource, metric_readers=[readerConsole, readerOtlp])
        metrics.set_meter_provider(meterProvider)

        # Local dictionaries to track spans and tokens so we can close them in the “after” hooks
        self._workflow_spans: dict[str, tuple[Span, AbstractContextManager]] = {}
        self._node_spans: dict[str, tuple[Span, AbstractContextManager]] = {}


    def before_workflow_execute(self, args: SpanOpenSchemaWorkflow):
        """
        Start a new workflow span, activate it, and store it so node spans will become children.
        """
        workflow_span = self._tracer.start_span(name=args.junjo_name)
        workflow_span.set_attribute("junjo.span_type", args.junjo_span_type)
        workflow_span.set_attribute("junjo.id", args.junjo_id)
        workflow_span.set_attribute("junjo.state_start", args.junjo_state_start)
        workflow_span.set_attribute("junjo.graph_json", args.junjo_graph_json)

        # Manually activate the workflow span. `token` is used to exit later.
        workflow_token = trace.use_span(workflow_span, end_on_exit=False)
        workflow_token.__enter__()

        # Store so we can finish and deactivate in after_workflow_execute.
        self._workflow_spans[args.junjo_id] = (workflow_span, workflow_token)


    def after_workflow_execute(self, args: SpanCloseSchemaWorkflow):
        """
        Finish the workflow span, set attributes (duration, etc.), and deactivate the span.
        """
        span_token_tuple = self._workflow_spans.pop(args.junjo_id, None)
        if span_token_tuple is not None:
            workflow_span, workflow_token = span_token_tuple

            # Record interesting workflow attributes
            workflow_span.set_attribute("junjo.state_end", args.junjo_state_end)

            # Deactivate the span
            workflow_token.__exit__(None, None, None)
            # End the span so it’s sent to the exporter
            workflow_span.end()


    # def before_node_execute(self, args: SpanOpenSchemaNode):
    #     """
    #     Start a new node span as a child of the *currently active* workflow span
    #     (assuming 'before_workflow_execute' activated the workflow span).
    #     """
    #     node_span = self._tracer.start_span(name=args.junjo_name)
    #     node_span.set_attribute("junjo.span_type", args.junjo_span_type)
    #     node_span.set_attribute("junjo.workflow_id", args.junjo_workflow_id)

    #     node_token = trace.use_span(node_span, end_on_exit=False)
    #     node_token.__enter__()
    #     self._node_spans[args.junjo_id] = (node_span, node_token)


    # def after_node_execute(self, args: SpanCloseSchemaNode):
    #     """
    #     Finish the node span, record attributes, and exit the node context.
    #     """
    #     span_token_tuple = self._node_spans.pop(args.junjo_id, None)
    #     if span_token_tuple is not None:
    #         node_span, node_token = span_token_tuple

    #         # Optionally record node details
    #         node_span.set_attribute("junjo.state_patch", args.junjo_state_patch)

    #         # Exit context and end the span
    #         node_token.__exit__(None, None, None)
    #         node_span.end()
