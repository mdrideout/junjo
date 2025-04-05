from enum import StrEnum

JUNJO_OTEL_MODULE_NAME = "junjo"

class JunjoOtelSpanTypes(StrEnum):
    """The type of Junjo opentelemetry spans."""
    WORKFLOW = "workflow"
    NODE = "node"
    NODE_GATHER = "node_gather"
