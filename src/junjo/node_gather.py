import asyncio

from opentelemetry import trace

from junjo.node import Node
from junjo.store import BaseStore
from junjo.telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME, JunjoOtelSpanTypes
from junjo.util import generate_safe_id


class NodeGather(Node):
    """
    Execute a list of nodes concurrently using asyncio.gather
    """

    def __init__(self, name:str, nodes: list[Node]):
        """
        Initializes the NodeGather.

        Args:
            nodes: A list of nodes to execute with asyncio.gather.
        """
        super().__init__()
        self.nodes = nodes
        self._id = generate_safe_id()
        self._name = name

    def __repr__(self):
        """Returns a string representation of the node."""
        return f"<{type(self).__name__} id={self.id}>"

    @property
    def id(self) -> str:
        """Returns the unique identifier for the node."""
        return self._id

    @property
    def name(self) -> str:
        return self._name

    async def service(self, store: BaseStore) -> None:
        """
        The core logic executed by this NodeGather node.
        It runs the contained nodes concurrently.
        """
        print(f"Executing concurrent nodes within {self.name} ({self.id})")
        if not self.nodes:
            return

        # Use self.id (from base Node class) as the parent_id for nested executions
        # Assuming the base Node's execute method handles span creation
        tasks = [node.execute(self.id, store) for node in self.nodes]
        await asyncio.gather(*tasks)

        print(f"Finished concurrent nodes within {self.name} ({self.id})")


    async def execute(self, parent_id: str, store: BaseStore) -> None:
        """
        Executes the nodes in the list.

        Args:
            parent_id: The parent id of the workflow.
            store: The store to use for the nodes.
        """

        # Acquire a tracer (will be a real tracer if configured, otherwise no-op)
        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)

        # Start a new span and keep a reference to the span object
        with tracer.start_as_current_span(self.name) as span:
            try:
                # Set an attribute on the span
                span.set_attribute("junjo.span_type", JunjoOtelSpanTypes.NODE_GATHER)
                span.set_attribute("junjo.parent_id", parent_id)
                span.set_attribute("junjo.id", self.id)

                # Perform your async operation
                await self.service(store)

            except Exception as e:
                print(f"Error executing node service: {e}")
                span.set_status(trace.StatusCode.ERROR, str(e))
                span.record_exception(e)
                raise
