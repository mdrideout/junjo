from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from opentelemetry import trace

from junjo.node import Node
from junjo.store import BaseStore
from junjo.telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME, JunjoOtelSpanTypes
from junjo.util import generate_safe_id

if TYPE_CHECKING:
    from junjo.workflow import Subflow

class RunConcurrent(Node):
    """
    Execute a list of nodes or subflows concurrently using asyncio.gather
    """

    def __init__(self, name:str, items: list[Node | Subflow]):
        """
        Initializes RunConcurrent.

        Args:
            items: A list of nodes or subflows to execute with asyncio.gather.
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
        The core logic executed by this RunConcurrent node or subflow.
        It runs the contained items concurrently.
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
        Executes the items in the list.

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
