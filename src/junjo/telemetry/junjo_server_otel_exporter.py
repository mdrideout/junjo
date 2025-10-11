from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace.export import BatchSpanProcessor


class JunjoServerOtelExporter:
    """
    Export OpenTelemetry data to Junjo Server.

    Junjo Server is capable of parsing and displaying enhanced
    Graph Workflow visualizations, and data specific to Graph Workflow debugging.
    """

    def __init__(
        self,
        host: str,
        port: str,
        api_key: str,
        insecure: bool = False,
    ):
        """
        Export OpenTelemetry data to Junjo Server.

        Junjo is designed to be compatible with existing OpenTelemetry configurations,
        by adding to an existing configuration instead of creating a new one.

        If you have not already configured OpenTelemetry for your application,
        follow these instructions: TODO: Add instructions.

        Args:
        - host: the hostname of the Junjo Server.
        - port: the port of the Junjo Server.
        - api_key: the API key for the Junjo Server.
        - insecure: whether to allow insecure connections to the Junjo Server.
        """

        # Set Class Instance Vars
        self._host = host
        self._port = port
        self._api_key = api_key
        self._insecure = insecure

        # Set the endpoint for the Junjo Server
        self._endpoint = f"{self._host}:{self._port}"

        # Define headers
        exporter_headers = (("x-junjo-api-key", self._api_key),)

        # Set OTLP Span Exporter for Junjo Server
        oltp_exporter = OTLPSpanExporter(
            endpoint=self._endpoint,
            insecure=self._insecure,
            headers=exporter_headers,
            timeout=120
        )
        self._span_processor = BatchSpanProcessor(oltp_exporter)

        # --- Add Metric Reader ---
        self._metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=self._endpoint,
                insecure=self._insecure,
                headers=exporter_headers,
            )
        )

    @property
    def span_processor(self):
        return self._span_processor

    @property
    def metric_reader(self):
        return self._metric_reader

    def flush(self, timeout_millis: float = 120000) -> bool:
        """
        Flush all pending telemetry manually.

        This method blocks until all telemetry is exported or the timeout is reached.
        It leverages the existing retry/timeout logic in the underlying gRPC exporters.
        It can be used to force a flush of all pending telemetry before the application exits.

        Args:
            timeout_millis: Maximum time to wait for flush in milliseconds.
                           Defaults to 120000ms (120 seconds) to match the
                           exporter timeout and allow for retries.

        Returns:
            True if all telemetry was flushed successfully, False otherwise.
        """
        success = True

        # Flush span processor
        try:
            if not self._span_processor.force_flush(int(timeout_millis)):
                success = False
        except Exception:
            success = False

        # Flush metric reader
        try:
            if not self._metric_reader.force_flush(timeout_millis):
                success = False
        except Exception:
            success = False

        return success
