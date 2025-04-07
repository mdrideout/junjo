from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from opentelemetry import trace

from junjo.graph import Graph
from junjo.node import Node
from junjo.state import BaseState
from junjo.store import BaseStore
from junjo.telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME, JunjoOtelSpanTypes
from junjo.util import generate_safe_id
from junjo.workflow import Workflow

# Generic for the parent store
StoreP = TypeVar("StoreP", bound="BaseStore")

# Generic for the subflow workflow store and state
StoreC = TypeVar("StoreC", bound="BaseStore")
StateC = TypeVar("StateC", bound=BaseState)

class SubFlow(Generic[StoreP, StateC, StoreC], ABC):
    """
    Execute a workflow within a workflow.
    """

    def __init__(self, name:str, graph: Graph, store: StoreC):
        """
        Initialize the SubFlow

        Args:
            graph: A graph to execute within a SubFlow Workflow.
        """
        super().__init__()
        self._name = name
        self.graph = graph
        self.store = store
        self._id = generate_safe_id()


    def __repr__(self):
        """Returns a string representation of the SubFlow."""
        return f"<{type(self).__name__} id={self.id}>"

    @property
    def id(self) -> str:
        """Returns the unique identifier for the SubFlow."""
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def node(self) -> Node[StoreC]:
        class SubFlowNode(Node[self.store]):
            """
            A node for the post_run_actions
            """
            async def service(self, store: StoreC) -> None:
                pass
        return SubFlowNode()

    @property
    def workflow(self) -> Workflow[StateC, StoreC]:
        return Workflow(
            workflow_name=self.name,
            graph=self.graph,
            store=self.store,
        )





    @abstractmethod
    async def post_run_actions(self, parent_store: StoreP) -> None:
        """Post run actions that can update the parent store."""
        raise NotImplementedError

    async def service(self) -> None:
        """
        The core logic to execute the SubFlow
        """
        print(f"Executing Subflow within {self.name} ({self.id})")
        await self.workflow.execute()

        print(f"Finished concurrent nodes within {self.name} ({self.id})")


    async def execute(self, parent_id: str) -> None:
        """
        Executes the SubFlow.

        Args:
            parent_id: The parent id of the SubFlow.
            store: The store to use for the nodes.
        """

        # Acquire a tracer (will be a real tracer if configured, otherwise no-op)
        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)

        # Start a new span and keep a reference to the span object
        with tracer.start_as_current_span(self.name) as span:
            try:
                # Set an attribute on the span
                span.set_attribute("junjo.span_type", JunjoOtelSpanTypes.SUB_FLOW)
                span.set_attribute("junjo.parent_id", parent_id)
                span.set_attribute("junjo.id", self.id)

                # Perform your async operation
                await self.service()

            except Exception as e:
                print(f"Error executing node service: {e}")
                span.set_status(trace.StatusCode.ERROR, str(e))
                span.record_exception(e)
                raise
