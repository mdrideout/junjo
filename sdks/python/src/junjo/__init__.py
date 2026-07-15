"""Typed, observable execution for explicit Workflows and bounded Agents.

Junjo provides Graph primitives for deterministic Workflow traversal and a
provider-neutral Agent kernel for bounded runtime Tool selection. Both
executables emit structured OpenTelemetry evidence and return detached typed
results.
"""
import logging

from .agent import (
    Agent,
    AgentConfigurationError,
    AgentError,
    AgentExecutionError,
    AgentExecutionResult,
    AgentLimits,
    AgentRunContext,
    AgentStateSnapshot,
    ModelDriver,
    ModelDriverBinding,
    ModelDriverDescriptor,
    Tool,
)
from .condition import Condition
from .correlation import ExecutionCorrelation
from .edge import Edge
from .eval import NodeEvaluationResult, evaluate_node
from .graph import (
    CompiledEdge,
    CompiledGraph,
    CompiledNode,
    Graph,
    GraphCompilationError,
    GraphRenderError,
    GraphSerializationError,
    GraphValidationError,
)
from .hooks import Hooks
from .node import Node
from .run_concurrent import RunConcurrent
from .state import BaseState
from .store import BaseStore
from .workflow import (
    ExecutionResult,
    GraphFactory,
    StoreFactory,
    Subflow,
    Workflow,
)
from .workflow_errors import WorkflowCancelledError, WorkflowExecutionError

logging.getLogger("junjo").addHandler(logging.NullHandler())

__all__ = [
    "Agent",
    "AgentConfigurationError",
    "AgentError",
    "AgentExecutionError",
    "AgentExecutionResult",
    "AgentLimits",
    "AgentRunContext",
    "AgentStateSnapshot",
    "Condition",
    "Graph",
    "CompiledGraph",
    "CompiledNode",
    "CompiledEdge",
    "GraphValidationError",
    "GraphCompilationError",
    "GraphSerializationError",
    "GraphRenderError",
    "Hooks",
    "ModelDriver",
    "ModelDriverBinding",
    "ModelDriverDescriptor",
    "GraphFactory",
    "StoreFactory",
    "ExecutionResult",
    "ExecutionCorrelation",
    "NodeEvaluationResult",
    "evaluate_node",
    "Workflow",
    "WorkflowCancelledError",
    "WorkflowExecutionError",
    "Subflow",
    "Tool",
    "Node",
    "RunConcurrent",
    "BaseState",
    "BaseStore",
    "Edge",
]
