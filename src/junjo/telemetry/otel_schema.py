from enum import StrEnum


class JunjoOtelSpanTypes(StrEnum):
    """The type of Junjo opentelemetry spans."""
    WORKFLOW = "workflow"
    NODE = "node"
