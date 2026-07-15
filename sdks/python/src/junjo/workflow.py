from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType, NoneType
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar, cast

from opentelemetry import trace

from ._identity import (
    ActiveExecutableIdentity,
    ExecutableType,
    active_executable_identity,
    get_active_executable_identity,
)
from ._json import require_ijson_text
from ._lifecycle import (
    GraphStoreLifecycleContext,
    LifecycleDispatcher,
)
from ._terminal import drain_terminal_work
from .correlation import (
    ExecutionCorrelation,
    _active_execution_correlation,
    _resolve_execution_correlation,
    _set_correlation_span_attributes,
)
from .hooks import Hooks
from .node import Node
from .run_concurrent import RunConcurrent
from .store import BaseStore, ParentStateT, ParentStoreT, StateT, StoreT
from .telemetry.diagnostics import cancellation_reason
from .telemetry.otel_schema import (
    JUNJO_OTEL_MODULE_NAME,
    JUNJO_TELEMETRY_CONTRACT_VERSION,
)
from .telemetry.payload import set_full_payload
from .telemetry.span_lifecycle import (
    get_span_identifiers,
    mark_span_cancelled,
    mark_span_failed,
    record_span_exception,
)
from .telemetry.store_evidence import StoreOwnerEvidence
from .util import generate_safe_id
from .workflow_errors import WorkflowCancelledError, WorkflowExecutionError

if TYPE_CHECKING:
    from .graph import CompiledGraph, Graph


_CovariantStoreT = TypeVar("_CovariantStoreT", bound="BaseStore", covariant=True)


logger = logging.getLogger("junjo.workflow")


class StoreFactory(Protocol, Generic[_CovariantStoreT]):
    """
    A callable that returns a new instance of a workflow's store.

    This factory is invoked at the beginning of each
    :meth:`~junjo.workflow.Workflow.execute` or
    :meth:`~junjo.workflow.Subflow.execute` call to ensure fresh, isolated
    state for that execution.
    """

    def __call__(self, *args, **kw) -> _CovariantStoreT: ...


_CovariantGraphT = TypeVar("_CovariantGraphT", bound="Graph", covariant=True)


class GraphFactory(Protocol, Generic[_CovariantGraphT]):
    """
    A callable that returns a new instance of a workflow's graph.

    This factory is invoked at the beginning of each
    :meth:`~junjo.workflow.Workflow.execute` or
    :meth:`~junjo.workflow.Subflow.execute` call to ensure a fresh, isolated
    graph for that execution. This is critical for concurrency safety because
    nodes and subflows are runtime objects with per-run identities.
    """

    def __call__(self, *args, **kw) -> _CovariantGraphT: ...


@dataclass(slots=True)
class _ExecutionContext(Generic[StoreT]):
    """Holds per-run workflow state so execution does not depend on instance mutation."""

    run_id: str
    graph: Graph
    compiled_graph: CompiledGraph
    store: StoreT
    dispatcher: LifecycleDispatcher
    node_execution_counter: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionResult(Generic[StateT]):
    """
    Frozen result wrapper for a completed workflow or subflow execution.

    ``ExecutionResult`` is the public post-run API for accessing final state and
    execution metadata without exposing live runtime objects like the internal
    store or graph. The wrapper is immutable; ``state`` is a detached final
    state snapshot copied out of the run-local store.

    The result includes:

    - ``run_id``: The unique identifier for this specific execution.
    - ``definition_id``: The stable identifier of the workflow or subflow
      definition.
    - ``name``: The configured workflow or subflow name.
    - ``state``: The detached final state snapshot for the completed
      execution.
    - ``node_execution_counts``: Current-scope execution counts keyed by
      executable id.
    """

    run_id: str
    definition_id: str
    name: str
    state: StateT
    node_execution_counts: Mapping[str, int]


async def _collect_workflow_terminal_evidence(
    store: BaseStore[StateT],
) -> tuple[StateT, StoreOwnerEvidence]:
    """Collect the two terminal Store snapshots as one owned async unit."""

    state = await store.get_state()
    evidence = await store._get_store_owner_evidence()
    return state, evidence


@dataclass(frozen=True, slots=True)
class _WorkflowTerminalEvidenceResult(Generic[StateT]):
    """Value-form outcome so caller cancellation and evidence failure can coexist."""

    state: StateT | None
    evidence: StoreOwnerEvidence | None
    error: BaseException | None

    def __post_init__(self) -> None:
        complete = self.state is not None and self.evidence is not None and self.error is None
        failed = self.state is None and self.evidence is None and self.error is not None
        if not (complete or failed):
            raise ValueError("Workflow terminal evidence result must be complete or failed.")


async def _capture_workflow_terminal_evidence(
    store: BaseStore[StateT],
) -> _WorkflowTerminalEvidenceResult[StateT]:
    """Capture evidence failure as data while the drain retains caller cancellation."""

    try:
        state, evidence = await _collect_workflow_terminal_evidence(store)
    except (asyncio.CancelledError, Exception) as error:
        return _WorkflowTerminalEvidenceResult(
            state=None,
            evidence=None,
            error=error,
        )
    return _WorkflowTerminalEvidenceResult(
        state=state,
        evidence=evidence,
        error=None,
    )


class _NestableWorkflow(Generic[StateT, StoreT, ParentStateT, ParentStoreT]):
    """
    Shared execution implementation for :class:`Workflow` and :class:`Subflow`.

    This type should not be used directly. Consumers should instantiate
    :class:`Workflow` or subclass :class:`Subflow`.
    """

    def __init__(
        self,
        graph_factory: GraphFactory[Graph],
        store_factory: StoreFactory[StoreT],
        max_iterations: int = 100,
        hooks: Hooks | None = None,
        name: str | None = None,
    ):
        if name is not None:
            name = require_ijson_text(name, "Workflow name", nonempty=True)
        self._id = generate_safe_id()
        self._name = name
        self.max_iterations = max_iterations
        self.hooks = hooks
        self._graph_factory = graph_factory
        self._store_factory = store_factory

    @property
    def id(self) -> str:
        """Returns the stable definition identifier for this workflow object."""
        return self._id

    @property
    def name(self) -> str:
        """Returns the configured workflow name or the class name."""
        if self._name is not None:
            return self._name
        return self.__class__.__name__

    @property
    def span_type(self) -> ExecutableType:
        """Returns the OpenTelemetry span type for this executable."""
        if isinstance(self, Subflow):
            return ExecutableType.SUBFLOW
        return ExecutableType.WORKFLOW

    async def execute(  # noqa: C901
        self,
        parent_store: ParentStoreT | None = None,
        parent_id: str | None = None,
        *,
        validate_graph: bool = True,
        correlation: ExecutionCorrelation | None = None,
    ) -> ExecutionResult[StateT]:
        """
        Execute the workflow or subflow and return the final execution snapshot.

        Each call creates a fresh graph, a fresh store, a fresh run id, and a
        fresh lifecycle dispatcher. This keeps the workflow definition itself
        immutable and safe to reuse across concurrent runs.

        :param parent_store: The parent store when executing a subflow.
            Top-level workflows should omit this argument.
        :type parent_store: ParentStoreT | None
        :param parent_id: The parent workflow or subflow identifier when
            nested.
        :type parent_id: str | None
        :param validate_graph: Whether to run ``Graph.validate()`` on the
            fresh graph before execution starts. Defaults to ``True``.
        :type validate_graph: bool
        :param correlation: Optional trusted application identity for this
            execution tree. Nested Junjo executables inherit it and cannot
            replace it.
        :type correlation: ExecutionCorrelation | None
        :returns: A detached snapshot of the completed execution, including
            the final state and current-scope execution counts.
        :rtype: ExecutionResult[StateT]
        :raises WorkflowExecutionError: If an admitted execution fails. The
            original failure is available as ``error.__cause__``.
        :raises WorkflowCancelledError: If an admitted execution is cancelled.
            This remains an :class:`asyncio.CancelledError`.
        """
        effective_correlation = _resolve_execution_correlation(correlation)
        parent_active_identity = get_active_executable_identity()
        graph = self._graph_factory()
        if validate_graph:
            graph.validate()
        compiled_graph = graph.compile()
        ctx = _ExecutionContext(
            run_id=generate_safe_id(),
            graph=graph,
            compiled_graph=compiled_graph,
            store=self._store_factory(),
            dispatcher=LifecycleDispatcher(self.hooks),
        )
        ctx.store._set_lifecycle_context(
            GraphStoreLifecycleContext(
                dispatcher=ctx.dispatcher,
                run_id=ctx.run_id,
                executable_definition_id=self.id,
                name=self.name,
                executable_type=self.span_type,
                executable_runtime_id=ctx.run_id,
                executable_structural_id=ctx.compiled_graph.graph_structural_id,
                enclosing_graph_structural_id=ctx.compiled_graph.graph_structural_id,
                compiled_node_structural_ids_by_runtime_id=MappingProxyType(
                    {
                        compiled_node.node_runtime_id: compiled_node.node_structural_id
                        for compiled_node in ctx.compiled_graph.compiled_nodes
                    }
                ),
            )
        )

        graph_json = ctx.graph.serialize_to_json_string()
        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)
        prepared_terminal_event = None
        result: ExecutionResult[StateT] | None = None
        failure: Exception | None = None
        cancellation: asyncio.CancelledError | None = None
        terminal_delivery_cancellation: asyncio.CancelledError | None = None
        final_state: StateT | None = None
        terminalization_error: BaseException | None = None
        workflow_log_extra = {
            "run_id": ctx.run_id,
            "executable_definition_id": self.id,
            "executable_runtime_id": ctx.run_id,
            "span_type": str(self.span_type),
        }

        logger.debug(
            "Executing workflow %s (%s)",
            self.name,
            self.id,
            extra=workflow_log_extra,
        )

        with _active_execution_correlation(effective_correlation), tracer.start_as_current_span(self.name) as span:
            try:
                initial_store_evidence = await ctx.store._get_store_owner_evidence()
                set_full_payload(
                    span,
                    "junjo.workflow.state.start",
                    initial_store_evidence.state_start,
                )
                span.set_attribute(
                    "junjo.store.revision.start",
                    initial_store_evidence.revision_start,
                )
                span.set_attribute("junjo.workflow.execution_graph_snapshot", graph_json)
                span.set_attribute("junjo.workflow.store.id", ctx.store.id)
                span.set_attribute("junjo.telemetry.contract_version", JUNJO_TELEMETRY_CONTRACT_VERSION)
                span.set_attribute("junjo.span_type", self.span_type)
                span.set_attribute("junjo.executable_definition_id", self.id)
                span.set_attribute("junjo.executable_runtime_id", ctx.run_id)
                _set_correlation_span_attributes(span, effective_correlation)
                span.set_attribute(
                    "junjo.executable_structural_id",
                    ctx.compiled_graph.graph_structural_id,
                )
                span.set_attribute(
                    "junjo.enclosing_graph_structural_id",
                    ctx.compiled_graph.graph_structural_id,
                )
                if parent_id is not None:
                    span.set_attribute("junjo.parent_executable_definition_id", parent_id)

                if parent_active_identity is not None:
                    span.set_attribute(
                        "junjo.parent_executable_definition_id",
                        parent_active_identity.executable_definition_id,
                    )
                    span.set_attribute(
                        "junjo.parent_executable_runtime_id",
                        parent_active_identity.executable_runtime_id,
                    )
                    span.set_attribute(
                        "junjo.parent_executable_structural_id",
                        parent_active_identity.executable_structural_id,
                    )
                    span.set_attribute(
                        "junjo.parent_executable_type",
                        parent_active_identity.executable_type,
                    )

                if parent_store is not None and parent_store.id is not None:
                    span.set_attribute("junjo.workflow.parent_store.id", parent_store.id)

                with active_executable_identity(
                    ActiveExecutableIdentity(
                        executable_definition_id=self.id,
                        executable_name=self.name,
                        executable_type=self.span_type,
                        executable_runtime_id=ctx.run_id,
                        executable_structural_id=ctx.compiled_graph.graph_structural_id,
                    )
                ):
                    trace_id, span_id = get_span_identifiers(span)
                    await ctx.dispatcher.workflow_started(
                        run_id=ctx.run_id,
                        executable_definition_id=self.id,
                        name=self.name,
                        span_type=self.span_type,
                        store_id=ctx.store.id,
                        graph_json=graph_json,
                        trace_id=trace_id,
                        span_id=span_id,
                        executable_runtime_id=ctx.run_id,
                        executable_structural_id=ctx.compiled_graph.graph_structural_id,
                        enclosing_graph_structural_id=ctx.compiled_graph.graph_structural_id,
                        parent_executable_definition_id=(
                            parent_active_identity.executable_definition_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_runtime_id=(
                            parent_active_identity.executable_runtime_id if parent_active_identity is not None else None
                        ),
                        parent_executable_structural_id=(
                            parent_active_identity.executable_structural_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_type=(
                            parent_active_identity.executable_type if parent_active_identity is not None else None
                        ),
                    )

                    if isinstance(self, Subflow):
                        if parent_store is None:
                            raise ValueError("Subflow requires a parent store to execute pre_run_actions.")
                        await cast(
                            "Subflow[StateT, StoreT, ParentStateT, ParentStoreT]",
                            self,
                        ).pre_run_actions(
                            parent_store,
                            cast(StoreT, ctx.store),
                        )

                    current_executable = ctx.graph.source
                    while True:
                        if isinstance(current_executable, Subflow):
                            await current_executable.execute(
                                ctx.store,
                                self.id,
                                validate_graph=validate_graph,
                            )
                            ctx.node_execution_counter[current_executable.id] = (
                                ctx.node_execution_counter.get(current_executable.id, 0) + 1
                            )
                            if ctx.node_execution_counter[current_executable.id] > self.max_iterations:
                                raise ValueError(
                                    f"Node '{current_executable}' exceeded maximum execution count. "
                                    "Check for loops in your graph. Ensure it transitions to a declared sink."
                                )

                        if isinstance(current_executable, Node):
                            await current_executable.execute(ctx.store, self.id)

                            if isinstance(current_executable, RunConcurrent):
                                for item in current_executable.items:
                                    ctx.node_execution_counter[item.id] = ctx.node_execution_counter.get(item.id, 0) + 1
                                    if ctx.node_execution_counter[item.id] > self.max_iterations:
                                        raise ValueError(
                                            f"Node '{item}' exceeded maximum execution count. "
                                            "Check for loops in your graph. Ensure it transitions to a declared sink."
                                        )
                            else:
                                ctx.node_execution_counter[current_executable.id] = (
                                    ctx.node_execution_counter.get(current_executable.id, 0) + 1
                                )
                                if ctx.node_execution_counter[current_executable.id] > self.max_iterations:
                                    raise ValueError(
                                        f"Node '{current_executable}' exceeded maximum execution count. "
                                        "Check for loops in your graph. Ensure it transitions to a declared sink."
                                    )

                        if current_executable in ctx.graph.sinks:
                            logger.debug(
                                "Reached declared sink %s (%s); exiting workflow loop.",
                                current_executable.name,
                                current_executable.id,
                                extra=workflow_log_extra,
                            )
                            break

                        current_executable = await ctx.graph.get_next_node(
                            ctx.store,
                            current_executable,
                        )

                    logger.debug(
                        "Completed workflow %s (%s)",
                        self.name,
                        self.id,
                        extra=workflow_log_extra,
                    )

                    if isinstance(self, Subflow):
                        if parent_store is None:
                            raise ValueError("Subflow requires a parent store to execute post_run_actions.")
                        logger.debug(
                            "Performing post-run actions for subflow %s (%s)",
                            self.name,
                            self.id,
                            extra=workflow_log_extra,
                        )
                        await cast(
                            "Subflow[StateT, StoreT, ParentStateT, ParentStoreT]",
                            self,
                        ).post_run_actions(
                            parent_store,
                            cast(StoreT, ctx.store),
                        )

            except asyncio.CancelledError as exc:
                mark_span_cancelled(span, exc)
                cancellation = exc

            except Exception as exc:
                logger.exception(
                    "Workflow execution failed for %s (%s)",
                    self.name,
                    self.id,
                    extra=workflow_log_extra,
                )
                mark_span_failed(span, exc)
                record_span_exception(span, exc)
                failure = exc

            finally:
                execution_sum = sum(ctx.node_execution_counter.values())
                final_state = ctx.store._get_last_known_state()
                final_store_evidence: StoreOwnerEvidence | None = None
                finalization_cancellation: asyncio.CancelledError | None = None
                evidence_result, finalization_cancellation = await drain_terminal_work(
                    _capture_workflow_terminal_evidence(ctx.store)
                )
                if evidence_result.error is None:
                    assert evidence_result.state is not None
                    assert evidence_result.evidence is not None
                    final_state = evidence_result.state
                    final_store_evidence = evidence_result.evidence
                else:
                    terminalization_error = evidence_result.error
                    record_span_exception(span, evidence_result.error)
                    span.set_attribute("junjo.store.reconstructable", False)
                    if cancellation is None and failure is None:
                        if isinstance(evidence_result.error, Exception):
                            failure = evidence_result.error
                        else:
                            failure = RuntimeError("Workflow terminal Store evidence collection was cancelled.")
                            failure.__cause__ = evidence_result.error
                        mark_span_failed(span, failure)
                trace_id, span_id = get_span_identifiers(span)

                if final_store_evidence is not None:
                    set_full_payload(
                        span,
                        "junjo.workflow.state.end",
                        final_store_evidence.state_end,
                    )
                    span.set_attribute(
                        "junjo.store.revision.end",
                        final_store_evidence.revision_end,
                    )
                    span.set_attribute(
                        "junjo.store.transition.count",
                        final_store_evidence.transition_count,
                    )
                    span.set_attribute(
                        "junjo.store.reconstructable",
                        final_store_evidence.reconstructable,
                    )
                span.set_attribute("junjo.workflow.node.count", execution_sum)

                if cancellation is None and failure is None:
                    result = ExecutionResult(
                        run_id=ctx.run_id,
                        definition_id=self.id,
                        name=self.name,
                        state=final_state,
                        node_execution_counts=MappingProxyType(dict(ctx.node_execution_counter)),
                    )
                    prepared_terminal_event = ctx.dispatcher.workflow_completed(
                        run_id=ctx.run_id,
                        executable_definition_id=self.id,
                        name=self.name,
                        span_type=self.span_type,
                        result=result,
                        store_id=ctx.store.id,
                        trace_id=trace_id,
                        span_id=span_id,
                        executable_runtime_id=ctx.run_id,
                        executable_structural_id=ctx.compiled_graph.graph_structural_id,
                        enclosing_graph_structural_id=ctx.compiled_graph.graph_structural_id,
                        parent_executable_definition_id=(
                            parent_active_identity.executable_definition_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_runtime_id=(
                            parent_active_identity.executable_runtime_id if parent_active_identity is not None else None
                        ),
                        parent_executable_structural_id=(
                            parent_active_identity.executable_structural_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_type=(
                            parent_active_identity.executable_type if parent_active_identity is not None else None
                        ),
                    )
                elif cancellation is not None:
                    prepared_terminal_event = ctx.dispatcher.workflow_cancelled(
                        run_id=ctx.run_id,
                        executable_definition_id=self.id,
                        name=self.name,
                        span_type=self.span_type,
                        reason=cancellation_reason(cancellation),
                        state=final_state,
                        store_id=ctx.store.id,
                        trace_id=trace_id,
                        span_id=span_id,
                        executable_runtime_id=ctx.run_id,
                        executable_structural_id=ctx.compiled_graph.graph_structural_id,
                        enclosing_graph_structural_id=ctx.compiled_graph.graph_structural_id,
                        parent_executable_definition_id=(
                            parent_active_identity.executable_definition_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_runtime_id=(
                            parent_active_identity.executable_runtime_id if parent_active_identity is not None else None
                        ),
                        parent_executable_structural_id=(
                            parent_active_identity.executable_structural_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_type=(
                            parent_active_identity.executable_type if parent_active_identity is not None else None
                        ),
                    )
                elif failure is not None:
                    prepared_terminal_event = ctx.dispatcher.workflow_failed(
                        run_id=ctx.run_id,
                        executable_definition_id=self.id,
                        name=self.name,
                        span_type=self.span_type,
                        error=failure,
                        state=final_state,
                        store_id=ctx.store.id,
                        trace_id=trace_id,
                        span_id=span_id,
                        executable_runtime_id=ctx.run_id,
                        executable_structural_id=ctx.compiled_graph.graph_structural_id,
                        enclosing_graph_structural_id=ctx.compiled_graph.graph_structural_id,
                        parent_executable_definition_id=(
                            parent_active_identity.executable_definition_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_runtime_id=(
                            parent_active_identity.executable_runtime_id if parent_active_identity is not None else None
                        ),
                        parent_executable_structural_id=(
                            parent_active_identity.executable_structural_id
                            if parent_active_identity is not None
                            else None
                        ),
                        parent_executable_type=(
                            parent_active_identity.executable_type if parent_active_identity is not None else None
                        ),
                    )

                try:
                    await ctx.dispatcher.dispatch(prepared_terminal_event, terminal=True)
                except asyncio.CancelledError as exc:
                    terminal_delivery_cancellation = exc
                if terminal_delivery_cancellation is None:
                    terminal_delivery_cancellation = finalization_cancellation

        if terminal_delivery_cancellation is not None:
            assert final_state is not None
            raise WorkflowCancelledError(
                *terminal_delivery_cancellation.args,
                run_id=ctx.run_id,
                definition_id=self.id,
                name=self.name,
                state=final_state,
                node_execution_counts=ctx.node_execution_counter,
                state_is_terminal=terminalization_error is None,
                terminalization_error=terminalization_error,
            ) from terminal_delivery_cancellation
        if cancellation is not None:
            assert final_state is not None
            raise WorkflowCancelledError(
                *cancellation.args,
                run_id=ctx.run_id,
                definition_id=self.id,
                name=self.name,
                state=final_state,
                node_execution_counts=ctx.node_execution_counter,
                state_is_terminal=terminalization_error is None,
                terminalization_error=terminalization_error,
            ) from cancellation
        if failure is not None:
            assert final_state is not None
            raise WorkflowExecutionError(
                f"Workflow execution failed for {self.name}.",
                run_id=ctx.run_id,
                definition_id=self.id,
                name=self.name,
                state=final_state,
                node_execution_counts=ctx.node_execution_counter,
                state_is_terminal=terminalization_error is None,
                terminalization_error=terminalization_error,
            ) from failure
        assert result is not None
        return result


class Workflow(_NestableWorkflow[StateT, StoreT, NoneType, NoneType]):
    def __init__(
        self,
        graph_factory: GraphFactory[Graph],
        store_factory: StoreFactory[StoreT],
        max_iterations: int = 100,
        hooks: Hooks | None = None,
        name: str | None = None,
    ):
        """
        A Workflow is a top-level, executable collection of nodes and edges
        arranged as a graph. It manages its own state and store, distinct from
        any parent or sub-workflows.

        This class is generic and requires two type parameters for a convenient
        and type-safe developer experience:

        ``StateT`` is the type of state managed by this workflow and should be
        a subclass of :class:`~junjo.state.BaseState`. ``StoreT`` is the store
        type used by this workflow and should be a subclass of
        :class:`~junjo.store.BaseStore`.

        Every call to :meth:`~junjo.workflow.Workflow.execute` creates a fresh
        graph, a fresh store, and a fresh execution context. That makes a
        ``Workflow`` instance a reusable definition or blueprint rather than a
        mutable live-run container.

        :param name: An optional name for the workflow. If not provided, the
            class name is used.
        :type name: str | None, optional
        :param graph_factory: A callable that returns a new instance of the
            workflow's graph (``Graph``). This factory is invoked at the
            beginning of each :meth:`~junjo.workflow.Workflow.execute` call to
            ensure a fresh, isolated graph for that execution.
        :type graph_factory: GraphFactory[Graph]
        :param store_factory: A callable that returns a new instance of the
            workflow's store (``StoreT``). This factory is invoked at the
            beginning of each :meth:`~junjo.workflow.Workflow.execute` call to
            ensure a fresh store for that execution.
        :type store_factory: StoreFactory[StoreT]
        :param max_iterations: The maximum number of times any single node or
            subflow may run within one workflow execution. For
            :class:`~junjo.run_concurrent.RunConcurrent`, Junjo counts each
            child item in the concurrent group rather than the
            ``RunConcurrent`` wrapper itself. This helps detect accidental
            loops. Defaults to 100.
        :type max_iterations: int, optional
        :param hooks: An optional :class:`~junjo.hooks.Hooks` registry for
            observing workflow lifecycle events. Hooks are optional observers;
            they do not control OpenTelemetry instrumentation or workflow
            execution.
        :type hooks: Hooks | None, optional

        .. rubric:: Example without hooks

        .. code-block:: python

            workflow = Workflow[MyState, MyStore](
                name="demo_base_workflow",
                graph_factory=create_my_graph,
                store_factory=lambda: MyStore(initial_state=MyState()),
            )

            result = await workflow.execute()
            print(result.state.model_dump_json())

        .. rubric:: Example with hooks

        .. code-block:: python

            import logging

            hooks = Hooks()
            logger = logging.getLogger(__name__)

            def log_completed(event) -> None:
                logger.info(
                    "workflow completed %s %s %s",
                    event.name,
                    event.run_id,
                    event.result.state.model_dump(),
                )

            hooks.on_workflow_completed(log_completed)

            workflow = Workflow[MyState, MyStore](
                name="configured_workflow",
                graph_factory=create_my_graph,
                store_factory=lambda: MyStore(initial_state=MyState()),
                hooks=hooks,
            )

        .. rubric:: Passing Parameters to Factories

        To provide parameters to your ``graph_factory`` or ``store_factory``
        when you create a workflow, wrap the factory call in a ``lambda``.
        This creates an argument-less factory that closes over the dependencies
        you want to inject while preserving the fresh-per-run execution model.

        .. code-block:: python

            def create_graph_with_dependency(emulator: Emulator) -> Graph:
                return Graph(...)

            my_emulator = Emulator()

            workflow = Workflow[MyState, MyStore](
                name="configured_workflow",
                graph_factory=lambda: create_graph_with_dependency(my_emulator),
                store_factory=lambda: MyStore(initial_state=MyState()),
            )
        """
        super().__init__(
            graph_factory=graph_factory,
            store_factory=store_factory,
            max_iterations=max_iterations,
            hooks=hooks,
            name=name,
        )


class Subflow(_NestableWorkflow[StateT, StoreT, ParentStateT, ParentStoreT], ABC):
    def __init__(
        self,
        graph_factory: GraphFactory[Graph],
        store_factory: StoreFactory[StoreT],
        max_iterations: int = 100,
        hooks: Hooks | None = None,
        name: str | None = None,
    ):
        """
        A Subflow is a workflow that:

        - Executes within a parent workflow or parent subflow.
        - Has its own isolated state and store.
        - Can interact with its parent workflow state before and after
          execution via :meth:`pre_run_actions` and
          :meth:`post_run_actions`.

        Like top-level workflows, subflows create a fresh graph and a fresh
        store for every execution. The child run is isolated from the parent
        store except for the explicit handoff points provided by the pre- and
        post-run hooks.

        :param name: An optional name for the subflow. If not provided, the
            class name is used.
        :type name: str | None, optional
        :param graph_factory: A callable that returns a new instance of the
            subflow's graph (``Graph``). This factory is invoked at the
            beginning of each :meth:`~junjo.workflow.Subflow.execute` call to
            ensure a fresh, isolated graph for that execution.
        :type graph_factory: GraphFactory[Graph]
        :param store_factory: A callable that returns a new instance of the
            subflow's store (``StoreT``). This factory is invoked at the
            beginning of each :meth:`~junjo.workflow.Subflow.execute` call to
            ensure a fresh store for that execution.
        :type store_factory: StoreFactory[StoreT]
        :param max_iterations: The maximum number of times any single node or
            nested subflow may run within one subflow execution. For
            :class:`~junjo.run_concurrent.RunConcurrent`, Junjo counts each
            child item in the concurrent group rather than the
            ``RunConcurrent`` wrapper itself. Defaults to 100.
        :type max_iterations: int, optional
        :param hooks: An optional :class:`~junjo.hooks.Hooks` registry for
            observing lifecycle events emitted by this subflow.
        :type hooks: Hooks | None, optional

        .. rubric:: Example

        .. code-block:: python

            class ExampleSubflow(
                Subflow[SubflowState, SubflowStore, ParentState, ParentStore]
            ):
                async def pre_run_actions(self, parent_store, subflow_store):
                    parent_state = await parent_store.get_state()
                    await subflow_store.set_parameter(
                        {"parameter": parent_state.parameter}
                    )

                async def post_run_actions(self, parent_store, subflow_store):
                    subflow_state = await subflow_store.get_state()
                    await parent_store.set_subflow_result(subflow_state.result)

            example_subflow = ExampleSubflow(
                graph_factory=create_example_subflow_graph,
                store_factory=lambda: ExampleSubflowStore(
                    initial_state=ExampleSubflowState()
                ),
            )
        """
        super().__init__(
            graph_factory=graph_factory,
            store_factory=store_factory,
            max_iterations=max_iterations,
            hooks=hooks,
            name=name,
        )

    @abstractmethod
    async def pre_run_actions(
        self,
        parent_store: ParentStoreT,
        subflow_store: StoreT,
    ) -> None:
        """
        This method is called before the subflow has run.

        This is where you can pass initial state values from the parent workflow
        to the subflow store for this specific run.

        :param parent_store: The parent store to interact with.
        :type parent_store: ParentStoreT
        :param subflow_store: The store for this specific subflow execution.
        :type subflow_store: StoreT
        """
        raise NotImplementedError

    @abstractmethod
    async def post_run_actions(
        self,
        parent_store: ParentStoreT,
        subflow_store: StoreT,
    ) -> None:
        """
        This method is called after the subflow has run.

        This is where you can update the parent store with the results of the
        child workflow.

        :param parent_store: The parent store to update.
        :type parent_store: ParentStoreT
        :param subflow_store: The store for this specific subflow execution.
        :type subflow_store: StoreT
        """
        raise NotImplementedError
