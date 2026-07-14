from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from opentelemetry import trace

from ._identity import (
    ActiveExecutableIdentity,
    ExecutableType,
    active_executable_identity,
    get_active_executable_identity,
)
from ._json import require_ijson_text
from .correlation import (
    _get_active_execution_correlation,
    _set_correlation_span_attributes,
)
from .node import Node
from .store import BaseStore
from .telemetry.diagnostics import cancellation_reason
from .telemetry.otel_schema import (
    JUNJO_OTEL_MODULE_NAME,
    JUNJO_TELEMETRY_CONTRACT_VERSION,
)
from .telemetry.span_lifecycle import (
    get_span_identifiers,
    mark_span_cancelled,
    mark_span_failed,
    record_span_exception,
)
from .util import generate_safe_id

if TYPE_CHECKING:
    from junjo.workflow import Subflow


logger = logging.getLogger("junjo.run_concurrent")


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

    The child membership is immutable after construction. Junjo stores
    ``items`` as a tuple so compiled graph snapshots, traversal, telemetry, and
    visualization stay aligned with the same graph shape.
    """

    def __init__(self, name: str, items: Sequence[Node | Subflow]):
        """
        :param name: The name of this collection of concurrently executed
            nodes.
        :type name: str
        :param items: A sequence of nodes or subflows to execute concurrently.
            Junjo copies this sequence into an immutable tuple during
            construction.
        :type items: Sequence[Node | Subflow]

        .. code-block:: python

            node_1 = NodeOne()
            node_2 = NodeTwo()
            node_3 = NodeThree()

            run_concurrent = RunConcurrent(
                name="Concurrent Execution",
                items=[node_1, node_2, node_3],
            )
        """
        name = require_ijson_text(name, "RunConcurrent name", nonempty=True)
        super().__init__()
        self._items = tuple(items)
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

    @property
    def items(self) -> tuple[Node | Subflow, ...]:
        """Return the immutable child executables for this concurrent group."""
        return self._items

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
        lifecycle_context = store._lifecycle_context
        run_concurrent_log_extra = {
            "run_id": (
                lifecycle_context.run_id
                if lifecycle_context is not None
                else None
            ),
            "executable_definition_id": self.id,
            "executable_runtime_id": self.id,
            "span_type": "run_concurrent",
        }
        logger.debug(
            "Executing concurrent items within %s (%s)",
            self.name,
            self.id,
            extra=run_concurrent_log_extra,
        )
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

        logger.debug(
            "Finished concurrent items within %s (%s)",
            self.name,
            self.id,
            extra=run_concurrent_log_extra,
        )

    async def execute(self, store: BaseStore, parent_id: str) -> None:  # noqa: C901
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
        terminal_delivery_cancellation: asyncio.CancelledError | None = None
        parent_active_identity = get_active_executable_identity()
        run_id = lifecycle_context.run_id if lifecycle_context is not None else None
        run_concurrent_structural_id = (
            lifecycle_context.compiled_node_structural_ids_by_runtime_id[self.id]
            if lifecycle_context is not None
            else None
        )
        if lifecycle_context is not None:
            assert run_concurrent_structural_id is not None
        run_concurrent_log_extra = {
            "run_id": run_id,
            "executable_definition_id": self.id,
            "executable_runtime_id": self.id,
            "span_type": "run_concurrent",
        }

        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)
        with tracer.start_as_current_span(self.name) as span:
            try:
                span.set_attribute("junjo.telemetry.contract_version", JUNJO_TELEMETRY_CONTRACT_VERSION)
                span.set_attribute("junjo.span_type", "run_concurrent")
                span.set_attribute("junjo.executable_definition_id", self.id)
                span.set_attribute("junjo.parent_executable_definition_id", parent_id)
                span.set_attribute("junjo.executable_runtime_id", self.id)
                _set_correlation_span_attributes(
                    span,
                    _get_active_execution_correlation(),
                )
                if run_concurrent_structural_id is not None:
                    span.set_attribute(
                        "junjo.executable_structural_id",
                        run_concurrent_structural_id,
                    )
                if lifecycle_context is not None:
                    span.set_attribute(
                        "junjo.enclosing_graph_structural_id",
                        lifecycle_context.enclosing_graph_structural_id,
                    )
                if parent_active_identity is not None:
                    span.set_attribute(
                        "junjo.parent_executable_runtime_id",
                        parent_active_identity.executable_runtime_id,
                    )
                    span.set_attribute(
                        "junjo.parent_executable_structural_id",
                        parent_active_identity.executable_structural_id,
                    )

                if lifecycle_context is not None:
                    assert run_concurrent_structural_id is not None
                    trace_id, span_id = get_span_identifiers(span)
                    await lifecycle_context.dispatcher.run_concurrent_started(
                        run_id=lifecycle_context.run_id,
                        executable_definition_id=self.id,
                        name=self.name,
                        parent_executable_definition_id=(
                            parent_active_identity.executable_definition_id
                            if parent_active_identity is not None
                            else lifecycle_context.executable_definition_id
                        ),
                        store_id=store.id,
                        trace_id=trace_id,
                        span_id=span_id,
                        executable_runtime_id=self.id,
                        executable_structural_id=run_concurrent_structural_id,
                        enclosing_graph_structural_id=(
                            lifecycle_context.enclosing_graph_structural_id
                        ),
                        parent_executable_runtime_id=(
                            parent_active_identity.executable_runtime_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_structural_id=(
                            parent_active_identity.executable_structural_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_type=(
                            parent_active_identity.executable_type
                            if parent_active_identity is not None
                            else None
                        ),
                    )

                if run_concurrent_structural_id is None:
                    await self.service(store)
                else:
                    with active_executable_identity(
                        ActiveExecutableIdentity(
                            executable_definition_id=self.id,
                            executable_name=self.name,
                            executable_type=ExecutableType.RUN_CONCURRENT,
                            executable_runtime_id=self.id,
                            executable_structural_id=run_concurrent_structural_id,
                        )
                    ):
                        await self.service(store)

                        if lifecycle_context is not None:
                            trace_id, span_id = get_span_identifiers(span)
                            prepared_terminal_event = lifecycle_context.dispatcher.run_concurrent_completed(
                                run_id=lifecycle_context.run_id,
                                executable_definition_id=self.id,
                                name=self.name,
                                parent_executable_definition_id=(
                                    parent_active_identity.executable_definition_id
                                    if parent_active_identity is not None
                                    else lifecycle_context.executable_definition_id
                                ),
                                store_id=store.id,
                                trace_id=trace_id,
                                span_id=span_id,
                                executable_runtime_id=self.id,
                                executable_structural_id=run_concurrent_structural_id,
                                enclosing_graph_structural_id=(
                                    lifecycle_context.enclosing_graph_structural_id
                                ),
                                parent_executable_runtime_id=(
                                    parent_active_identity.executable_runtime_id
                                    if parent_active_identity is not None
                                    else None
                                ),
                                parent_executable_structural_id=(
                                    parent_active_identity.executable_structural_id
                                    if parent_active_identity is not None
                                    else None
                                ),
                                parent_executable_type=(
                                    parent_active_identity.executable_type
                                    if parent_active_identity is not None
                                    else None
                                ),
                            )

            except asyncio.CancelledError as exc:
                mark_span_cancelled(span, exc)
                cancellation = exc
                if lifecycle_context is not None:
                    assert run_concurrent_structural_id is not None
                    trace_id, span_id = get_span_identifiers(span)
                    prepared_terminal_event = lifecycle_context.dispatcher.run_concurrent_cancelled(
                        run_id=lifecycle_context.run_id,
                        executable_definition_id=self.id,
                        name=self.name,
                        parent_executable_definition_id=(
                            parent_active_identity.executable_definition_id
                            if parent_active_identity is not None
                            else lifecycle_context.executable_definition_id
                        ),
                        store_id=store.id,
                        reason=cancellation_reason(exc),
                        trace_id=trace_id,
                        span_id=span_id,
                        executable_runtime_id=self.id,
                        executable_structural_id=run_concurrent_structural_id,
                        enclosing_graph_structural_id=(
                            lifecycle_context.enclosing_graph_structural_id
                        ),
                        parent_executable_runtime_id=(
                            parent_active_identity.executable_runtime_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_structural_id=(
                            parent_active_identity.executable_structural_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_type=(
                            parent_active_identity.executable_type
                            if parent_active_identity is not None
                            else None
                        ),
                    )

            except Exception as exc:
                if lifecycle_context is None:
                    logger.exception(
                        "RunConcurrent execution failed for %s (%s)",
                        self.name,
                        self.id,
                        extra=run_concurrent_log_extra,
                    )
                mark_span_failed(span, exc)
                record_span_exception(span, exc)
                failure = exc
                if lifecycle_context is not None:
                    assert run_concurrent_structural_id is not None
                    trace_id, span_id = get_span_identifiers(span)
                    prepared_terminal_event = lifecycle_context.dispatcher.run_concurrent_failed(
                        run_id=lifecycle_context.run_id,
                        executable_definition_id=self.id,
                        name=self.name,
                        parent_executable_definition_id=(
                            parent_active_identity.executable_definition_id
                            if parent_active_identity is not None
                            else lifecycle_context.executable_definition_id
                        ),
                        store_id=store.id,
                        error=exc,
                        trace_id=trace_id,
                        span_id=span_id,
                        executable_runtime_id=self.id,
                        executable_structural_id=run_concurrent_structural_id,
                        enclosing_graph_structural_id=(
                            lifecycle_context.enclosing_graph_structural_id
                        ),
                        parent_executable_runtime_id=(
                            parent_active_identity.executable_runtime_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_structural_id=(
                            parent_active_identity.executable_structural_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_type=(
                            parent_active_identity.executable_type
                            if parent_active_identity is not None
                            else None
                        ),
                    )

            if lifecycle_context is not None:
                try:
                    await lifecycle_context.dispatcher.dispatch(
                        prepared_terminal_event,
                        terminal=True,
                    )
                except asyncio.CancelledError as exc:
                    terminal_delivery_cancellation = exc

        if terminal_delivery_cancellation is not None:
            raise terminal_delivery_cancellation
        if cancellation is not None:
            raise cancellation
        if failure is not None:
            raise failure
