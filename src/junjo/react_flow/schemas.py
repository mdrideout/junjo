
from pydantic import BaseModel


class ReactFlowPosition(BaseModel):
    x: float
    y: float

class ReactFlowNodeData(BaseModel):
    label: str

class ReactFlowNode(BaseModel):
    id: str
    data: ReactFlowNodeData
    position: ReactFlowPosition

class ReactFlowEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None

class ReactFlowViewport(BaseModel):
    x: float
    y: float
    zoom: float

class ReactFlowJsonObject(BaseModel):
    nodes: list[ReactFlowNode]
    edges: list[ReactFlowEdge]
    viewport: ReactFlowViewport
