from enum import StrEnum

JUNJO_OTEL_MODULE_NAME = "junjo"

class JunjoOtelSpanTypes(StrEnum):
    """The type of Junjo opentelemetry spans."""
    WORKFLOW = "workflow"
    SUBFLOW = "subflow"
    NODE = "node"
    RUN_CONCURRENT = "run_concurrent"
