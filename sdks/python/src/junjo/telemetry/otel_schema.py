from .._identity import ExecutableType

JUNJO_OTEL_MODULE_NAME = "junjo"
JUNJO_TELEMETRY_CONTRACT_VERSION = 3


def span_type_value(executable_type: ExecutableType) -> str:
    """Map a lifecycle executable kind to its OpenTelemetry string value."""

    return executable_type.value
