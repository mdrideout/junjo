
from pydantic import BaseModel


class SpanOpenSchemaWorkflow(BaseModel):
    """Attributes needed to open the workflow span."""
    junjo_span_type: str = "junjo_workflow"
    junjo_id: str
    junjo_name: str
    junjo_state_start: str
    junjo_graph_json: str

class SpanCloseSchemaWorkflow(BaseModel):
    """Attributes needed to close the workflow span."""
    junjo_id: str
    junjo_state_end: str


class SpanOpenSchemaNode(BaseModel):
    """Attributes needed to open the node span."""
    junjo_span_type: str = "junjo_node"
    junjo_workflow_id: str
    junjo_id: str
    junjo_name: str

class SpanCloseSchemaNode(BaseModel):
    """Attributes needed to close the node span."""
    junjo_id: str
    junjo_state_patch: str
