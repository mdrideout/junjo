import logging

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("junjo.telemetry")


class JunjoOtelExporter:
    """
    Configure Junjo AI Studio trace export for an existing OpenTelemetry setup.

    Junjo is designed to be compatible with existing OpenTelemetry
    configurations by adding a span processor instead of creating or replacing
    the application's tracer provider.

    Junjo AI Studio currently accepts OTLP traces only. This exporter therefore
    exposes a :attr:`span_processor` and does not create a meter provider,
    metric reader, or periodic metric-export worker. Applications that export
    metrics to another OpenTelemetry destination should configure that metric
    pipeline independently.

    In normal applications, the tracer provider remains the top-level owner of
    shutdown. Call ``TracerProvider.shutdown()`` when the process is
    terminating.

    :meth:`flush` is available for a manual local queue drain when you truly
    need it, such as in short-lived scripts or tests. :meth:`shutdown` is a
    wrapper-local helper that shuts down only the Junjo-owned span processor.

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
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        # Retrieve API key from environment
        JUNJO_AI_STUDIO_API_KEY = os.getenv("JUNJO_AI_STUDIO_API_KEY")
        resource = Resource.create({"service.name": "my-ai-workflow"})

        # Application running directly on the local machine
        junjo_exporter = JunjoOtelExporter(
            host="localhost",
            port="26155",
            api_key=JUNJO_AI_STUDIO_API_KEY,
            insecure=True,
        )

        # If the application instead runs on Studio's Docker network, replace
        # the block above with this endpoint (localhost resolves to the app
        # container itself):
        # junjo_exporter = JunjoOtelExporter(
        #     host="ingestion",
        #     port="26155",
        #     api_key=JUNJO_AI_STUDIO_API_KEY,
        #     insecure=True,
        # )

        # Add Junjo AI Studio trace export to your tracer provider
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(junjo_exporter.span_processor)
        trace.set_tracer_provider(tracer_provider)

        # On application shutdown:
        tracer_provider.shutdown()

    .. rubric:: Production Deployment

    For a production environment with TLS enabled, such as one behind a
    reverse proxy like Caddy:

    .. code-block:: python

        import os
        from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        # Retrieve API key from environment
        JUNJO_AI_STUDIO_API_KEY = os.getenv("JUNJO_AI_STUDIO_API_KEY")
        resource = Resource.create({"service.name": "my-ai-workflow"})

        junjo_exporter_prod = JunjoOtelExporter(
            host="ingestion.junjo.example.com",  # Your domain
            port="443",  # HTTPS port
            api_key=JUNJO_AI_STUDIO_API_KEY,
            insecure=False,  # TLS enabled
        )

        # Add Junjo AI Studio trace export to your tracer provider
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(junjo_exporter_prod.span_processor)
        trace.set_tracer_provider(tracer_provider)

        # On application shutdown:
        tracer_provider.shutdown()
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
        otlp_exporter = OTLPSpanExporter(
            endpoint=self._endpoint,
            insecure=self._insecure,
            headers=exporter_headers,
            timeout=120,
        )
        self._span_processor = BatchSpanProcessor(otlp_exporter)

    @property
    def span_processor(self) -> BatchSpanProcessor:
        """Returns the configured span processor."""
        return self._span_processor

    def shutdown(self) -> bool:
        """
        Shut down the Junjo-owned span processor.

        In most applications, the preferred terminal lifecycle is to shut down
        the owning ``TracerProvider``. This helper is provided for cases where
        you need to shut down only the Junjo-owned span processor directly.

        :returns: ``True`` if the span processor shuts down cleanly, ``False``
                  if shutdown raises. Failures are logged through the
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

        return success

    def flush(self, timeout_millis: float = 120000) -> bool:
        """
        Request a manual drain of pending local telemetry.

        Use it only when a short-lived script or test needs to ask the local
        batch processor to drain before normal provider shutdown.

        OpenTelemetry's batch processor does not propagate collector acceptance
        or durability through ``force_flush()``. A ``True`` result therefore
        confirms only that the processor reported its local drain complete; it
        is not proof that Studio accepted or persisted the spans. Verify remote
        delivery through Studio's query APIs when that guarantee matters. The
        installed OpenTelemetry processor may also apply its timeout as a best-
        effort budget rather than a strict deadline.

        In normal applications, shut down the owning ``TracerProvider`` instead
        of using :meth:`flush` as the standard exit path.

        :param timeout_millis: Best-effort local processor budget requested for
                               the drain, in milliseconds. The installed
                               OpenTelemetry processor may not enforce it as a
                               strict deadline. Defaults to 120000ms (120
                               seconds).
        :type timeout_millis: float
        :returns: ``True`` if the span processor reports its local drain
                  complete, ``False`` if it refuses or raises. This does not
                  attest collector acceptance. Surfaced failures are logged
                  through the ``junjo.telemetry`` logger.
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

        return success
