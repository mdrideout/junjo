from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from opentelemetry import trace

from .store import BaseStore
from .telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME, JunjoOtelSpanTypes
from .util import generate_safe_id

if TYPE_CHECKING:
    pass

class RunForEvery:
    """
    Execute a Node, Subflow, or RunConcurrent for each item in a list.

    An instance of RunForEvery can be added to a workflow's graph the same was as any other node.
    """

    def __init__(self, name:str, items: list[Any]):
        """
        Args:
            name: The name of this collection of concurrently executed nodes.
            items: A list of nodes or subflows to execute with asyncio.gather.

        .. code-block:: python

            node_1 = NodeOne()
            node_2 = NodeTwo()
            node_3 = NodeThree()

            run_concurrent = RunConcurrent(
                name="Concurrent Execution",
                items=[node_1, node_2, node_3]
            )
        """
        super().__init__()
        self.items = items
        self._id = generate_safe_id()
        self._name = name

    def __repr__(self):
        """Returns a string representation of the node or subflow."""
        return f"<{type(self).__name__} id={self.id}>"

    @property
    def id(self) -> str:
        """Returns the unique identifier for the node or subflow."""
        return self._id

    @property
    def name(self) -> str:
        return self._name

    async def service(self, store: BaseStore) -> None:
        """
        Execute the provided nodes and subflows concurrently using asyncio.gather.
        """
        print(f"Executing concurrent items within {self.name} ({self.id})")
        if not self.items:
            return

        # Execute all items concurrently
        # Using asyncio.gather to run all items concurrently
        tasks = [item.execute(store, self.id) for item in self.items]
        await asyncio.gather(*tasks)

        print(f"Finished concurrent items within {self.name} ({self.id})")


    async def execute(self, store: BaseStore, parent_id: str) -> None:
        """
        Execute the RunConcurrent node's service function with OpenTelemetry tracing.
        This method is responsible for tracing and error handling.

        Args:
            store: The store to use for the items.
            parent_id: The parent id of the workflow.
        """

        # Acquire a tracer (will be a real tracer if configured, otherwise no-op)
        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)

        # Start a new span and keep a reference to the span object
        with tracer.start_as_current_span(self.name) as span:
            try:
                # Set an attribute on the span
                span.set_attribute("junjo.span_type", JunjoOtelSpanTypes.RUN_CONCURRENT)
                span.set_attribute("junjo.parent_id", parent_id)
                span.set_attribute("junjo.id", self.id)

                # Perform your async operation
                await self.service(store)

            except Exception as e:
                print(f"Error executing node service: {e}")
                span.set_status(trace.StatusCode.ERROR, str(e))
                span.record_exception(e)
                raise
