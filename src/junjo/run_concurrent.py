from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from opentelemetry import trace

from .node import Node
from .store import BaseStore
from .telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME, JunjoOtelSpanTypes
from .telemetry.span_lifecycle import mark_span_cancelled
from .util import generate_safe_id

if TYPE_CHECKING:
    from junjo.workflow import Subflow

class RunConcurrent(Node):
    """
    Execute a list of nodes or subflows concurrently. Under the hood, this uses asyncio.gather
    to run all items concurrently.

    An instance of RunConcurrent can be added to a workflow's graph the same was as any other node.
    """

    def __init__(self, name:str, items: list[Node | Subflow]):
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

    async def _cancel_pending_tasks(
        self,
        pending: set[asyncio.Task[None]],
        reason: str,
    ) -> None:
        for task in pending:
            task.cancel(reason)

        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def _get_first_failure(
        self,
        done: set[asyncio.Task[None]],
    ) -> Exception | None:
        for task in done:
            try:
                task.result()
            except asyncio.CancelledError:
                continue
            except Exception as exc:  # noqa: PERF203
                return exc

        return None

    async def service(self, store: BaseStore) -> None:
        """
        Execute the provided nodes and subflows concurrently.
        If one item fails, cancel all still-pending siblings and re-raise the original error.
        """
        print(f"Executing concurrent items within {self.name} ({self.id})")
        if not self.items:
            return

        pending = {
            asyncio.create_task(item.execute(store, self.id))
            for item in self.items
        }

        try:
            done, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_EXCEPTION,
            )

            failure = self._get_first_failure(done)

            if failure is not None:
                await self._cancel_pending_tasks(pending, "sibling_failed")
                pending.clear()

                raise failure

            for task in done:
                task.result()

        except asyncio.CancelledError:
            await self._cancel_pending_tasks(pending, "cancelled")

            raise

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

            except asyncio.CancelledError as exc:
                mark_span_cancelled(span, exc)
                raise

            except Exception as e:
                print(f"Error executing node service: {e}")
                span.set_status(trace.StatusCode.ERROR, str(e))
                span.record_exception(e)
                raise
