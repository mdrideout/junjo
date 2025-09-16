import backoff
import grpc
from loguru import logger
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .junjo_server.proto_gen import auth_pb2, auth_pb2_grpc


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
        self._token = None

        # Authenticate with Junjo Server
        self._authenticate()

        # Set the endpoint for the Junjo Server
        self._endpoint = f"{self._host}:{self._port}"

        # Define headers
        exporter_headers = (
            ("authorization", f"Bearer {self._token}"),
        )

        # Set OTLP Span Exporter for Junjo Server
        oltp_exporter = OTLPSpanExporter(endpoint=self._endpoint, insecure=self._insecure, headers=exporter_headers)
        self._span_processor = BatchSpanProcessor(oltp_exporter)

        # --- Add Metric Reader ---
        self._metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=self._endpoint, insecure=self._insecure, headers=exporter_headers)
        )

    @backoff.on_exception(backoff.expo, grpc.RpcError, max_tries=5)
    def _authenticate(self):
        """
        Authenticate with the Junjo Server and get a JWT.
        """
        logger.info("Authenticating with Junjo Server...")
        channel = grpc.insecure_channel(f"{self._host}:{self._port}")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        request = auth_pb2.GetTokenRequest(api_key=self._api_key)
        response = stub.GetToken(request)
        self._token = response.jwt
        logger.info("Successfully authenticated with Junjo Server.")
        logger.debug(f"Received JWT: {self._token}")

    @property
    def span_processor(self):
        return self._span_processor

    @property
    def metric_reader(self):
        return self._metric_reader
