from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from opentelemetry import trace

from .node import Node
from .store import BaseStore
from .telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME
from .telemetry.span_lifecycle import get_span_identifiers, mark_span_cancelled
from .util import generate_safe_id

if TYPE_CHECKING:
    from junjo.workflow import Subflow


class RunConcurrent(Node):
    """
    Execute a list of nodes or subflows concurrently.

    An instance of ``RunConcurrent`` can be added to a workflow graph the same
    way as any other node. Under the hood it starts one task per child item and
    waits for them to settle.

    If one child fails, Junjo cancels all still-pending siblings and re-raises
    the original failure. Cancelled siblings are marked as cancelled in
    telemetry rather than as errors so traces tell the full story of the
    failure boundary.
    """

    def __init__(self, name: str, items: list[Node | Subflow]):
        """
        :param name: The name of this collection of concurrently executed
            nodes.
        :type name: str
        :param items: A list of nodes or subflows to execute concurrently.
        :type items: list[Node | Subflow]

        .. code-block:: python

            node_1 = NodeOne()
            node_2 = NodeTwo()
            node_3 = NodeThree()

            run_concurrent = RunConcurrent(
                name="Concurrent Execution",
                items=[node_1, node_2, node_3],
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
        """Returns the configured name of this concurrent execution group."""
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

        Child items receive the same run-local store. If one item fails, all
        still-pending siblings are cancelled and the original failure is
        re-raised once the cancellations have been drained.
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
        Execute the ``RunConcurrent`` node with tracing and lifecycle dispatch.

        This wraps :meth:`service` with a dedicated run-concurrent span and the
        same started/completed/failed/cancelled lifecycle semantics used by
        ordinary nodes.

        :param store: The run-local store for the current workflow execution.
        :type store: BaseStore
        :param parent_id: The parent workflow or subflow identifier.
        :type parent_id: str
        """
        lifecycle_context = store._lifecycle_context
        prepared_terminal_event = None
        failure: Exception | None = None
        cancellation: asyncio.CancelledError | None = None

        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)
        with tracer.start_as_current_span(self.name) as span:
            try:
                span.set_attribute("junjo.span_type", "run_concurrent")
                span.set_attribute("junjo.parent_id", parent_id)
                span.set_attribute("junjo.id", self.id)

                if lifecycle_context is not None:
                    trace_id, span_id = get_span_identifiers(span)
                    await lifecycle_context.dispatcher.run_concurrent_started(
                        run_id=lifecycle_context.run_id,
                        definition_id=self.id,
                        name=self.name,
                        parent_definition_id=lifecycle_context.definition_id,
                        store_id=store.id,
                        trace_id=trace_id,
                        span_id=span_id,
                    )

                await self.service(store)

                if lifecycle_context is not None:
                    trace_id, span_id = get_span_identifiers(span)
                    prepared_terminal_event = lifecycle_context.dispatcher.run_concurrent_completed(
                        run_id=lifecycle_context.run_id,
                        definition_id=self.id,
                        name=self.name,
                        parent_definition_id=lifecycle_context.definition_id,
                        store_id=store.id,
                        trace_id=trace_id,
                        span_id=span_id,
                    )

            except asyncio.CancelledError as exc:
                mark_span_cancelled(span, exc)
                cancellation = exc
                if lifecycle_context is not None:
                    trace_id, span_id = get_span_identifiers(span)
                    prepared_terminal_event = lifecycle_context.dispatcher.run_concurrent_cancelled(
                        run_id=lifecycle_context.run_id,
                        definition_id=self.id,
                        name=self.name,
                        parent_definition_id=lifecycle_context.definition_id,
                        store_id=store.id,
                        reason=str(exc.args[0]) if exc.args else "cancelled",
                        trace_id=trace_id,
                        span_id=span_id,
                    )

            except Exception as exc:
                print(f"Error executing node service: {exc}")
                span.set_status(trace.StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                failure = exc
                if lifecycle_context is not None:
                    trace_id, span_id = get_span_identifiers(span)
                    prepared_terminal_event = lifecycle_context.dispatcher.run_concurrent_failed(
                        run_id=lifecycle_context.run_id,
                        definition_id=self.id,
                        name=self.name,
                        parent_definition_id=lifecycle_context.definition_id,
                        store_id=store.id,
                        error=exc,
                        trace_id=trace_id,
                        span_id=span_id,
                    )

        if lifecycle_context is not None:
            await lifecycle_context.dispatcher.dispatch(prepared_terminal_event)

        if cancellation is not None:
            raise cancellation
        if failure is not None:
            raise failure
