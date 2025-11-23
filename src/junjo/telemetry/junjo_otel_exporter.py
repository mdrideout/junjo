from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace.export import BatchSpanProcessor


class JunjoOtelExporter:
    """
    An OpenTelemetry SpanExporter that sends spans to the Junjo AI Studio.
    """

    def __init__(
        self,
        host: str,
        port: str,
        api_key: str,
        insecure: bool = False,
    ):
        """
        Export OpenTelemetry data to Junjo AI Studio.

        Junjo is designed to be compatible with existing OpenTelemetry configurations,
        by adding to an existing configuration instead of creating a new one.

        If you have not already configured OpenTelemetry for your application,
        follow these instructions: TODO: Add instructions.

        :param host: The hostname of the Junjo AI Studio.
        :type host: str
        :param port: The port of the Junjo AI Studio.
        :type port: str
        :param api_key: The API key for the Junjo AI Studio.
        :type api_key: str
        :param insecure: Whether to allow insecure connections to the Junjo AI Studio.
                         Defaults to ``False``.
        :type insecure: bool
        """

        # Set Class Instance Vars
        self._host = host
        self._port = port
        self._api_key = api_key
        self._insecure = insecure

        # Set the endpoint for the Junjo AI Studio
        self._endpoint = f"{self._host}:{self._port}"

        # Define headers
        exporter_headers = (("x-junjo-api-key", self._api_key),)

        # Set OTLP Span Exporter for Junjo AI Studio
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
        """Returns the configured span processor."""
        return self._span_processor

    @property
    def metric_reader(self):
        """Returns the configured metric reader."""
        return self._metric_reader

    def flush(self, timeout_millis: float = 120000) -> bool:
        """
        Flush all pending telemetry manually.

        This method blocks until all telemetry is exported or the timeout is reached.
        It leverages the existing retry/timeout logic in the underlying gRPC exporters.
        It can be used to force a flush of all pending telemetry before the application exits.

        :param timeout_millis: Maximum time to wait for flush in milliseconds.
                               Defaults to 120000ms (120 seconds) to match the
                               exporter timeout and allow for retries.
        :type timeout_millis: float
        :returns: ``True`` if all telemetry was flushed successfully, ``False`` otherwise.
        :rtype: bool
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
