from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from opentelemetry import trace

from . import hooks as hook_events
from ._identity import ExecutableType
from .telemetry.diagnostics import (
    callable_identity,
    cancellation_reason,
    error_type,
    exception_message,
    exception_stacktrace,
    portable_diagnostic_text,
)

if TYPE_CHECKING:
    from .agent.errors import AgentExecutionError
    from .agent.result import AgentExecutionResult
    from .agent.state import AgentStateSnapshot
    from .hooks import Hooks
    from .state import BaseState
    from .workflow import ExecutionResult


StateT = TypeVar("StateT", bound="BaseState")


@dataclass(frozen=True, slots=True)
class PreparedHookEvent:
    event_name: str
    event: hook_events.LifecycleEvent


@dataclass(frozen=True, slots=True)
class AgentLifecycleIdentity:
    """Run-local identity required by every public Agent lifecycle event."""

    run_id: str
    executable_definition_id: str
    name: str
    agent_key: str
    store_id: str
    trace_id: str
    span_id: str
    executable_structural_id: str
    parent_executable_definition_id: str | None
    parent_executable_runtime_id: str | None
    parent_executable_structural_id: str | None
    parent_executable_type: ExecutableType | None


@dataclass(slots=True)
class GraphStoreLifecycleContext:
    dispatcher: LifecycleDispatcher
    run_id: str
    executable_definition_id: str
    name: str
    executable_type: ExecutableType
    executable_runtime_id: str
    executable_structural_id: str
    enclosing_graph_structural_id: str
    compiled_node_structural_ids_by_runtime_id: Mapping[str, str]


class LifecycleDispatcher:
    def __init__(self, hooks: Hooks | None) -> None:
        self._callbacks = hooks._snapshot() if hooks is not None else {}

    async def dispatch(
        self,
        prepared: PreparedHookEvent | None,
        *,
        terminal: bool = False,
    ) -> None:
        if prepared is None:
            return

        task = asyncio.current_task()
        cancellation_count_at_start = task.cancelling() if task is not None else 0
        for callback in self._callbacks.get(prepared.event_name, ()):
            try:
                result = callback(prepared.event)
                if inspect.isawaitable(result):
                    await result
            except asyncio.CancelledError as exc:
                current_count = task.cancelling() if task is not None else 0
                if current_count > cancellation_count_at_start:
                    if terminal:
                        self._record_hook_delivery_cancelled(prepared.event_name, callback, exc)
                    raise
                self._record_hook_error(prepared.event_name, callback, exc)
            except Exception as exc:
                self._record_hook_error(prepared.event_name, callback, exc)

    async def workflow_started(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        span_type: ExecutableType,
        store_id: str,
        graph_json: str,
        trace_id: str,
        span_id: str,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_definition_id: str | None,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> None:
        event_name = "subflow_started" if span_type is ExecutableType.SUBFLOW else "workflow_started"
        event_kwargs = {
            "run_id": run_id,
            "executable_definition_id": executable_definition_id,
            "name": name,
            "trace_id": trace_id,
            "span_id": span_id,
            "executable_type": span_type,
            "store_id": store_id,
            "graph_json": graph_json,
            "executable_runtime_id": executable_runtime_id,
            "executable_structural_id": executable_structural_id,
            "enclosing_graph_structural_id": enclosing_graph_structural_id,
            "parent_executable_definition_id": parent_executable_definition_id,
            "parent_executable_runtime_id": parent_executable_runtime_id,
            "parent_executable_structural_id": parent_executable_structural_id,
            "parent_executable_type": parent_executable_type,
        }
        event = (
            hook_events.SubflowStartedEvent(**event_kwargs)
            if span_type is ExecutableType.SUBFLOW
            else hook_events.WorkflowStartedEvent(**event_kwargs)
        )
        await self.dispatch(PreparedHookEvent(event_name, event))

    def workflow_completed(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        span_type: ExecutableType,
        result: ExecutionResult[StateT],
        store_id: str,
        trace_id: str,
        span_id: str,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_definition_id: str | None,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        event_name = "subflow_completed" if span_type is ExecutableType.SUBFLOW else "workflow_completed"
        event_kwargs = {
            "run_id": run_id,
            "executable_definition_id": executable_definition_id,
            "name": name,
            "trace_id": trace_id,
            "span_id": span_id,
            "executable_type": span_type,
            "result": result,
            "store_id": store_id,
            "executable_runtime_id": executable_runtime_id,
            "executable_structural_id": executable_structural_id,
            "enclosing_graph_structural_id": enclosing_graph_structural_id,
            "parent_executable_definition_id": parent_executable_definition_id,
            "parent_executable_runtime_id": parent_executable_runtime_id,
            "parent_executable_structural_id": parent_executable_structural_id,
            "parent_executable_type": parent_executable_type,
        }
        event = (
            hook_events.SubflowCompletedEvent(**event_kwargs)
            if span_type is ExecutableType.SUBFLOW
            else hook_events.WorkflowCompletedEvent(**event_kwargs)
        )
        return PreparedHookEvent(event_name, event)

    def workflow_failed(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        span_type: ExecutableType,
        error: Exception,
        state: StateT,
        store_id: str,
        trace_id: str,
        span_id: str,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_definition_id: str | None,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        event_name = "subflow_failed" if span_type is ExecutableType.SUBFLOW else "workflow_failed"
        event_kwargs = {
            "run_id": run_id,
            "executable_definition_id": executable_definition_id,
            "name": name,
            "trace_id": trace_id,
            "span_id": span_id,
            "executable_type": span_type,
            "error": error,
            "state": state,
            "store_id": store_id,
            "executable_runtime_id": executable_runtime_id,
            "executable_structural_id": executable_structural_id,
            "enclosing_graph_structural_id": enclosing_graph_structural_id,
            "parent_executable_definition_id": parent_executable_definition_id,
            "parent_executable_runtime_id": parent_executable_runtime_id,
            "parent_executable_structural_id": parent_executable_structural_id,
            "parent_executable_type": parent_executable_type,
        }
        event = (
            hook_events.SubflowFailedEvent(**event_kwargs)
            if span_type is ExecutableType.SUBFLOW
            else hook_events.WorkflowFailedEvent(**event_kwargs)
        )
        return PreparedHookEvent(event_name, event)

    def workflow_cancelled(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        span_type: ExecutableType,
        reason: str,
        state: StateT,
        store_id: str,
        trace_id: str,
        span_id: str,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_definition_id: str | None,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        event_name = "subflow_cancelled" if span_type is ExecutableType.SUBFLOW else "workflow_cancelled"
        event_kwargs = {
            "run_id": run_id,
            "executable_definition_id": executable_definition_id,
            "name": name,
            "trace_id": trace_id,
            "span_id": span_id,
            "executable_type": span_type,
            "reason": reason,
            "state": state,
            "store_id": store_id,
            "executable_runtime_id": executable_runtime_id,
            "executable_structural_id": executable_structural_id,
            "enclosing_graph_structural_id": enclosing_graph_structural_id,
            "parent_executable_definition_id": parent_executable_definition_id,
            "parent_executable_runtime_id": parent_executable_runtime_id,
            "parent_executable_structural_id": parent_executable_structural_id,
            "parent_executable_type": parent_executable_type,
        }
        event = (
            hook_events.SubflowCancelledEvent(**event_kwargs)
            if span_type is ExecutableType.SUBFLOW
            else hook_events.WorkflowCancelledEvent(**event_kwargs)
        )
        return PreparedHookEvent(event_name, event)

    async def node_started(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        parent_executable_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> None:
        await self.dispatch(
            PreparedHookEvent(
                "node_started",
                hook_events.NodeStartedEvent(
                    run_id=run_id,
                    executable_definition_id=executable_definition_id,
                    name=name,
                    trace_id=trace_id,
                    span_id=span_id,
                    executable_type=ExecutableType.NODE,
                    parent_executable_definition_id=parent_executable_definition_id,
                    store_id=store_id,
                    executable_runtime_id=executable_runtime_id,
                    executable_structural_id=executable_structural_id,
                    enclosing_graph_structural_id=enclosing_graph_structural_id,
                    parent_executable_runtime_id=parent_executable_runtime_id,
                    parent_executable_structural_id=parent_executable_structural_id,
                    parent_executable_type=parent_executable_type,
                ),
            )
        )

    def node_completed(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        parent_executable_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        return PreparedHookEvent(
            "node_completed",
            hook_events.NodeCompletedEvent(
                run_id=run_id,
                executable_definition_id=executable_definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                executable_type=ExecutableType.NODE,
                parent_executable_definition_id=parent_executable_definition_id,
                store_id=store_id,
                executable_runtime_id=executable_runtime_id,
                executable_structural_id=executable_structural_id,
                enclosing_graph_structural_id=enclosing_graph_structural_id,
                parent_executable_runtime_id=parent_executable_runtime_id,
                parent_executable_structural_id=parent_executable_structural_id,
                parent_executable_type=parent_executable_type,
            ),
        )

    def node_failed(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        parent_executable_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        error: Exception,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        return PreparedHookEvent(
            "node_failed",
            hook_events.NodeFailedEvent(
                run_id=run_id,
                executable_definition_id=executable_definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                executable_type=ExecutableType.NODE,
                parent_executable_definition_id=parent_executable_definition_id,
                store_id=store_id,
                error=error,
                executable_runtime_id=executable_runtime_id,
                executable_structural_id=executable_structural_id,
                enclosing_graph_structural_id=enclosing_graph_structural_id,
                parent_executable_runtime_id=parent_executable_runtime_id,
                parent_executable_structural_id=parent_executable_structural_id,
                parent_executable_type=parent_executable_type,
            ),
        )

    def node_cancelled(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        parent_executable_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        reason: str,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        return PreparedHookEvent(
            "node_cancelled",
            hook_events.NodeCancelledEvent(
                run_id=run_id,
                executable_definition_id=executable_definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                executable_type=ExecutableType.NODE,
                parent_executable_definition_id=parent_executable_definition_id,
                store_id=store_id,
                reason=reason,
                executable_runtime_id=executable_runtime_id,
                executable_structural_id=executable_structural_id,
                enclosing_graph_structural_id=enclosing_graph_structural_id,
                parent_executable_runtime_id=parent_executable_runtime_id,
                parent_executable_structural_id=parent_executable_structural_id,
                parent_executable_type=parent_executable_type,
            ),
        )

    async def run_concurrent_started(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        parent_executable_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> None:
        await self.dispatch(
            PreparedHookEvent(
                "run_concurrent_started",
                hook_events.RunConcurrentStartedEvent(
                    run_id=run_id,
                    executable_definition_id=executable_definition_id,
                    name=name,
                    trace_id=trace_id,
                    span_id=span_id,
                    executable_type=ExecutableType.RUN_CONCURRENT,
                    parent_executable_definition_id=parent_executable_definition_id,
                    store_id=store_id,
                    executable_runtime_id=executable_runtime_id,
                    executable_structural_id=executable_structural_id,
                    enclosing_graph_structural_id=enclosing_graph_structural_id,
                    parent_executable_runtime_id=parent_executable_runtime_id,
                    parent_executable_structural_id=parent_executable_structural_id,
                    parent_executable_type=parent_executable_type,
                ),
            )
        )

    def run_concurrent_completed(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        parent_executable_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        return PreparedHookEvent(
            "run_concurrent_completed",
            hook_events.RunConcurrentCompletedEvent(
                run_id=run_id,
                executable_definition_id=executable_definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                executable_type=ExecutableType.RUN_CONCURRENT,
                parent_executable_definition_id=parent_executable_definition_id,
                store_id=store_id,
                executable_runtime_id=executable_runtime_id,
                executable_structural_id=executable_structural_id,
                enclosing_graph_structural_id=enclosing_graph_structural_id,
                parent_executable_runtime_id=parent_executable_runtime_id,
                parent_executable_structural_id=parent_executable_structural_id,
                parent_executable_type=parent_executable_type,
            ),
        )

    def run_concurrent_failed(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        parent_executable_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        error: Exception,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        return PreparedHookEvent(
            "run_concurrent_failed",
            hook_events.RunConcurrentFailedEvent(
                run_id=run_id,
                executable_definition_id=executable_definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                executable_type=ExecutableType.RUN_CONCURRENT,
                parent_executable_definition_id=parent_executable_definition_id,
                store_id=store_id,
                error=error,
                executable_runtime_id=executable_runtime_id,
                executable_structural_id=executable_structural_id,
                enclosing_graph_structural_id=enclosing_graph_structural_id,
                parent_executable_runtime_id=parent_executable_runtime_id,
                parent_executable_structural_id=parent_executable_structural_id,
                parent_executable_type=parent_executable_type,
            ),
        )

    def run_concurrent_cancelled(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        parent_executable_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        reason: str,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        return PreparedHookEvent(
            "run_concurrent_cancelled",
            hook_events.RunConcurrentCancelledEvent(
                run_id=run_id,
                executable_definition_id=executable_definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                executable_type=ExecutableType.RUN_CONCURRENT,
                parent_executable_definition_id=parent_executable_definition_id,
                store_id=store_id,
                reason=reason,
                executable_runtime_id=executable_runtime_id,
                executable_structural_id=executable_structural_id,
                enclosing_graph_structural_id=enclosing_graph_structural_id,
                parent_executable_runtime_id=parent_executable_runtime_id,
                parent_executable_structural_id=parent_executable_structural_id,
                parent_executable_type=parent_executable_type,
            ),
        )

    async def state_changed(
        self,
        *,
        run_id: str,
        executable_definition_id: str,
        name: str,
        span_type: ExecutableType,
        store_id: str,
        store_name: str,
        action_name: str,
        patch: str,
        state: StateT,
        parent_executable_definition_id: str,
        trace_id: str,
        span_id: str,
        executable_runtime_id: str,
        executable_structural_id: str,
        enclosing_graph_structural_id: str,
        parent_executable_runtime_id: str | None,
        parent_executable_structural_id: str | None,
        parent_executable_type: ExecutableType | None,
    ) -> None:
        await self.dispatch(
            PreparedHookEvent(
                "state_changed",
                hook_events.StateChangedEvent(
                    run_id=run_id,
                    executable_definition_id=executable_definition_id,
                    name=name,
                    trace_id=trace_id,
                    span_id=span_id,
                    executable_type=span_type,
                    store_id=store_id,
                    store_name=store_name,
                    action_name=action_name,
                    patch=patch,
                    state=state,
                    parent_executable_definition_id=parent_executable_definition_id,
                    executable_runtime_id=executable_runtime_id,
                    executable_structural_id=executable_structural_id,
                    enclosing_graph_structural_id=enclosing_graph_structural_id,
                    parent_executable_runtime_id=parent_executable_runtime_id,
                    parent_executable_structural_id=parent_executable_structural_id,
                    parent_executable_type=parent_executable_type,
                ),
            )
        )

    async def agent_started(self, identity: AgentLifecycleIdentity) -> None:
        """Dispatch the admitted Agent start event from common identity fields."""

        await self.dispatch(
            PreparedHookEvent(
                "agent_started",
                hook_events.AgentStartedEvent(
                    run_id=identity.run_id,
                    executable_definition_id=identity.executable_definition_id,
                    name=identity.name,
                    trace_id=identity.trace_id,
                    span_id=identity.span_id,
                    executable_type=ExecutableType.AGENT,
                    executable_runtime_id=identity.run_id,
                    executable_structural_id=identity.executable_structural_id,
                    parent_executable_definition_id=identity.parent_executable_definition_id,
                    parent_executable_runtime_id=identity.parent_executable_runtime_id,
                    parent_executable_structural_id=identity.parent_executable_structural_id,
                    parent_executable_type=identity.parent_executable_type,
                    agent_key=identity.agent_key,
                    store_id=identity.store_id,
                ),
            )
        )

    def agent_completed(
        self,
        *,
        identity: AgentLifecycleIdentity,
        result: AgentExecutionResult,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        return PreparedHookEvent(
            "agent_completed",
            hook_events.AgentCompletedEvent(
                run_id=identity.run_id,
                executable_definition_id=identity.executable_definition_id,
                name=identity.name,
                trace_id=identity.trace_id,
                span_id=identity.span_id,
                executable_type=ExecutableType.AGENT,
                executable_runtime_id=identity.run_id,
                executable_structural_id=identity.executable_structural_id,
                parent_executable_definition_id=identity.parent_executable_definition_id,
                parent_executable_runtime_id=identity.parent_executable_runtime_id,
                parent_executable_structural_id=identity.parent_executable_structural_id,
                parent_executable_type=identity.parent_executable_type,
                agent_key=identity.agent_key,
                store_id=identity.store_id,
                result=result,
            ),
        )

    def agent_failed(
        self,
        *,
        identity: AgentLifecycleIdentity,
        error: AgentExecutionError,
        state: AgentStateSnapshot,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        return PreparedHookEvent(
            "agent_failed",
            hook_events.AgentFailedEvent(
                run_id=identity.run_id,
                executable_definition_id=identity.executable_definition_id,
                name=identity.name,
                trace_id=identity.trace_id,
                span_id=identity.span_id,
                executable_type=ExecutableType.AGENT,
                executable_runtime_id=identity.run_id,
                executable_structural_id=identity.executable_structural_id,
                parent_executable_definition_id=identity.parent_executable_definition_id,
                parent_executable_runtime_id=identity.parent_executable_runtime_id,
                parent_executable_structural_id=identity.parent_executable_structural_id,
                parent_executable_type=identity.parent_executable_type,
                agent_key=identity.agent_key,
                store_id=identity.store_id,
                error=error,
                state=state,
            ),
        )

    def agent_cancelled(
        self,
        *,
        identity: AgentLifecycleIdentity,
        reason: str,
        state: AgentStateSnapshot,
    ) -> PreparedHookEvent | None:
        if not self._callbacks:
            return None
        return PreparedHookEvent(
            "agent_cancelled",
            hook_events.AgentCancelledEvent(
                run_id=identity.run_id,
                executable_definition_id=identity.executable_definition_id,
                name=identity.name,
                trace_id=identity.trace_id,
                span_id=identity.span_id,
                executable_type=ExecutableType.AGENT,
                executable_runtime_id=identity.run_id,
                executable_structural_id=identity.executable_structural_id,
                parent_executable_definition_id=identity.parent_executable_definition_id,
                parent_executable_runtime_id=identity.parent_executable_runtime_id,
                parent_executable_structural_id=identity.parent_executable_structural_id,
                parent_executable_type=identity.parent_executable_type,
                agent_key=identity.agent_key,
                store_id=identity.store_id,
                reason=reason,
                state=state,
            ),
        )

    def _record_hook_error(
        self,
        event_name: str,
        callback,
        exc: BaseException,
    ) -> None:
        span = trace.get_current_span()
        if not span.is_recording():
            return

        portable_event_name = portable_diagnostic_text(
            event_name,
            fallback="unknown_hook_event",
            nonempty=True,
        )
        message = exception_message(exc)
        error_attributes: dict[str, str] = {
            "junjo.hook.event": portable_event_name,
            "junjo.hook.callback": callable_identity(callback),
            "junjo.hook.error.type": error_type(exc),
            "junjo.hook.error.message": message,
            "exception.type": error_type(exc),
            "exception.message": message,
            "exception.stacktrace": exception_stacktrace(exc),
        }
        span.add_event("junjo.hook_error", error_attributes)

    def _record_hook_delivery_cancelled(
        self,
        event_name: str,
        callback,
        exc: asyncio.CancelledError,
    ) -> None:
        span = trace.get_current_span()
        if not span.is_recording():
            return

        span.add_event(
            "junjo.hook_delivery_cancelled",
            {
                "junjo.hook.event": portable_diagnostic_text(
                    event_name,
                    fallback="unknown_hook_event",
                    nonempty=True,
                ),
                "junjo.hook.callback": callable_identity(callback),
                "junjo.hook.delivery.cancelled_reason": cancellation_reason(exc),
            },
        )
