import logging

from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("junjo.telemetry")


class JunjoOtelExporter:
    """
    Configure Junjo AI Studio OTLP components for an existing OpenTelemetry setup.

    Junjo is designed to be compatible with existing OpenTelemetry configurations,
    by adding to an existing configuration instead of creating a new one.

    In normal applications, the tracer provider and meter provider remain the
    top-level owners of shutdown. Call ``TracerProvider.shutdown()`` and
    ``MeterProvider.shutdown()`` when the process is terminating.

    :meth:`flush` is available for manual immediate export when you truly need
    it, such as in short-lived scripts or tests. :meth:`shutdown` is a
    wrapper-local helper that shuts down only the Junjo-owned span processor
    and metric reader.

    :param host: The hostname of the Junjo AI Studio.
    :type host: str
    :param port: The port of the Junjo AI Studio.
    :type port: str
    :param api_key: The API key for the Junjo AI Studio.
    :type api_key: str
    :param insecure: Whether to allow insecure connections to the Junjo AI Studio.
                     Defaults to ``False``.
    :type insecure: bool

    .. rubric:: Local Development

    To send telemetry to a local Junjo AI Studio instance, such as one
    running through Docker Compose:

    .. code-block:: python

        import os
        from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry import trace

        # Retrieve API key from environment
        JUNJO_AI_STUDIO_API_KEY = os.getenv("JUNJO_AI_STUDIO_API_KEY")

        # Option 1: Using localhost
        junjo_exporter_local = JunjoOtelExporter(
            host="localhost",
            port="50051",
            api_key=JUNJO_AI_STUDIO_API_KEY,
            insecure=True,
        )

        # Option 2: Using Docker service name (if running in same Docker network)
        junjo_exporter_docker = JunjoOtelExporter(
            host="junjo-ai-studio-ingestion",  # Docker service name
            port="50051",
            api_key=JUNJO_AI_STUDIO_API_KEY,
            insecure=True,
        )

        # Add to your tracer provider
        provider = TracerProvider()
        provider.add_span_processor(junjo_exporter_local.span_processor)
        trace.set_tracer_provider(provider)

    .. rubric:: Production Deployment

    For a production environment with TLS enabled, such as one behind a
    reverse proxy like Caddy:

    .. code-block:: python

        import os
        from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry import trace

        # Retrieve API key from environment
        JUNJO_AI_STUDIO_API_KEY = os.getenv("JUNJO_AI_STUDIO_API_KEY")

        junjo_exporter_prod = JunjoOtelExporter(
            host="ingestion.junjo.example.com",  # Your domain
            port="443",  # HTTPS port
            api_key=JUNJO_AI_STUDIO_API_KEY,
            insecure=False,  # TLS enabled
        )

        # Add to your tracer provider
        provider = TracerProvider()
        provider.add_span_processor(junjo_exporter_prod.span_processor)
        trace.set_tracer_provider(provider)
    """

    def __init__(
        self,
        host: str,
        port: str,
        api_key: str,
        insecure: bool = False,
    ) -> None:
        """
        Initializes the JunjoOtelExporter.
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
    def span_processor(self) -> BatchSpanProcessor:
        """Returns the configured span processor."""
        return self._span_processor

    @property
    def metric_reader(self) -> PeriodicExportingMetricReader:
        """Returns the configured metric reader."""
        return self._metric_reader

    def shutdown(self, timeout_millis: float = 30000) -> bool:
        """
        Shut down the Junjo-owned telemetry components.

        In most applications, the preferred terminal lifecycle is to shut down
        the owning ``TracerProvider`` and ``MeterProvider``. This helper is
        provided for cases where you need to shut down only the Junjo-owned
        span processor and metric reader directly.

        :param timeout_millis: Maximum time to wait for metric reader shutdown
                               in milliseconds. Defaults to ``30000``.
        :type timeout_millis: float
        :returns: ``True`` if both components shut down cleanly, ``False`` if
                  either shutdown path raises. Failures are logged through the
                  ``junjo.telemetry`` logger.
        :rtype: bool
        """
        success = True
        exporter_log_extra = {"endpoint": self._endpoint}

        try:
            self._span_processor.shutdown()
        except Exception:
            success = False
            logger.warning(
                "Failed to shut down the Junjo span processor for endpoint %s.",
                self._endpoint,
                extra=exporter_log_extra,
                exc_info=True,
            )

        try:
            self._metric_reader.shutdown(timeout_millis=timeout_millis)
        except Exception:
            success = False
            logger.warning(
                "Failed to shut down the Junjo metric reader for endpoint %s.",
                self._endpoint,
                extra=exporter_log_extra,
                exc_info=True,
            )

        return success

    def flush(self, timeout_millis: float = 120000) -> bool:
        """
        Force a manual drain of pending telemetry.

        This method blocks until pending telemetry is exported or the timeout is
        reached. Use it only when you need an immediate manual export, such as
        in tests, short-lived scripts, or other environments where the normal
        provider shutdown lifecycle is not the right fit.

        In normal applications, shut down the owning ``TracerProvider`` and
        ``MeterProvider`` instead of using :meth:`flush` as the standard exit
        path.

        :param timeout_millis: Maximum time to wait for flush in milliseconds.
                               Defaults to 120000ms (120 seconds) to match the
                               exporter timeout and allow for retries.
        :type timeout_millis: float
        :returns: ``True`` if all telemetry was flushed successfully, ``False``
                  otherwise. Failures are logged through the
                  ``junjo.telemetry`` logger.
        :rtype: bool
        """
        success = True
        exporter_log_extra = {"endpoint": self._endpoint}

        # Flush span processor
        try:
            if not self._span_processor.force_flush(int(timeout_millis)):
                success = False
                logger.warning(
                    "Junjo span processor force_flush returned false for endpoint %s.",
                    self._endpoint,
                    extra=exporter_log_extra,
                )
        except Exception:
            success = False
            logger.warning(
                "Failed to force-flush the Junjo span processor for endpoint %s.",
                self._endpoint,
                extra=exporter_log_extra,
                exc_info=True,
            )

        # Flush metric reader
        try:
            if not self._metric_reader.force_flush(timeout_millis):
                success = False
                logger.warning(
                    "Junjo metric reader force_flush returned false for endpoint %s.",
                    self._endpoint,
                    extra=exporter_log_extra,
                )
        except Exception:
            success = False
            logger.warning(
                "Failed to force-flush the Junjo metric reader for endpoint %s.",
                self._endpoint,
                extra=exporter_log_extra,
                exc_info=True,
            )

        return success
