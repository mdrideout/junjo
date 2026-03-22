from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from opentelemetry import trace

from . import hooks as hook_events
from .telemetry.otel_schema import JUNJO_OTEL_MODULE_NAME, JunjoOtelSpanTypes

if TYPE_CHECKING:
    from .hooks import Hooks
    from .state import BaseState
    from .workflow import ExecutionResult


StateT = TypeVar("StateT", bound="BaseState")


@dataclass(frozen=True, slots=True)
class PreparedHookEvent:
    event_name: str
    event: hook_events.LifecycleEvent


@dataclass(slots=True)
class StoreLifecycleContext:
    dispatcher: LifecycleDispatcher
    run_id: str
    definition_id: str
    name: str
    span_type: JunjoOtelSpanTypes


class LifecycleDispatcher:
    def __init__(self, hooks: Hooks | None) -> None:
        self._hooks = hooks

    async def dispatch(self, prepared: PreparedHookEvent | None) -> None:
        if prepared is None or self._hooks is None:
            return

        for callback in self._hooks._callbacks_for(prepared.event_name):
            try:
                result = callback(prepared.event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                self._record_hook_error(prepared.event_name, callback, exc, prepared.event)

    async def workflow_started(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        span_type: JunjoOtelSpanTypes,
        store_id: str,
        graph_json: str,
        trace_id: str,
        span_id: str,
    ) -> None:
        event_name = "subflow_started" if span_type is JunjoOtelSpanTypes.SUBFLOW else "workflow_started"
        event_kwargs = {
            "run_id": run_id,
            "definition_id": definition_id,
            "name": name,
            "trace_id": trace_id,
            "span_id": span_id,
            "span_type": span_type,
            "store_id": store_id,
            "graph_json": graph_json,
        }
        event = (
            hook_events.SubflowStartedEvent(**event_kwargs)
            if span_type is JunjoOtelSpanTypes.SUBFLOW
            else hook_events.WorkflowStartedEvent(**event_kwargs)
        )
        await self.dispatch(PreparedHookEvent(event_name, event))

    def workflow_completed(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        span_type: JunjoOtelSpanTypes,
        result: ExecutionResult[StateT],
        store_id: str,
        trace_id: str,
        span_id: str,
    ) -> PreparedHookEvent | None:
        if self._hooks is None:
            return None
        event_name = "subflow_completed" if span_type is JunjoOtelSpanTypes.SUBFLOW else "workflow_completed"
        event_kwargs = {
            "run_id": run_id,
            "definition_id": definition_id,
            "name": name,
            "trace_id": trace_id,
            "span_id": span_id,
            "span_type": span_type,
            "result": result,
            "store_id": store_id,
        }
        event = (
            hook_events.SubflowCompletedEvent(**event_kwargs)
            if span_type is JunjoOtelSpanTypes.SUBFLOW
            else hook_events.WorkflowCompletedEvent(**event_kwargs)
        )
        return PreparedHookEvent(event_name, event)

    def workflow_failed(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        span_type: JunjoOtelSpanTypes,
        error: Exception,
        state: StateT,
        store_id: str,
        trace_id: str,
        span_id: str,
    ) -> PreparedHookEvent | None:
        if self._hooks is None:
            return None
        event_name = "subflow_failed" if span_type is JunjoOtelSpanTypes.SUBFLOW else "workflow_failed"
        event_kwargs = {
            "run_id": run_id,
            "definition_id": definition_id,
            "name": name,
            "trace_id": trace_id,
            "span_id": span_id,
            "span_type": span_type,
            "error": error,
            "state": state,
            "store_id": store_id,
        }
        event = (
            hook_events.SubflowFailedEvent(**event_kwargs)
            if span_type is JunjoOtelSpanTypes.SUBFLOW
            else hook_events.WorkflowFailedEvent(**event_kwargs)
        )
        return PreparedHookEvent(event_name, event)

    def workflow_cancelled(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        span_type: JunjoOtelSpanTypes,
        reason: str,
        state: StateT,
        store_id: str,
        trace_id: str,
        span_id: str,
    ) -> PreparedHookEvent | None:
        if self._hooks is None:
            return None
        event_name = "subflow_cancelled" if span_type is JunjoOtelSpanTypes.SUBFLOW else "workflow_cancelled"
        event_kwargs = {
            "run_id": run_id,
            "definition_id": definition_id,
            "name": name,
            "trace_id": trace_id,
            "span_id": span_id,
            "span_type": span_type,
            "reason": reason,
            "state": state,
            "store_id": store_id,
        }
        event = (
            hook_events.SubflowCancelledEvent(**event_kwargs)
            if span_type is JunjoOtelSpanTypes.SUBFLOW
            else hook_events.WorkflowCancelledEvent(**event_kwargs)
        )
        return PreparedHookEvent(event_name, event)

    async def node_started(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        parent_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
    ) -> None:
        await self.dispatch(
            PreparedHookEvent(
                "node_started",
                hook_events.NodeStartedEvent(
                    run_id=run_id,
                    definition_id=definition_id,
                    name=name,
                    trace_id=trace_id,
                    span_id=span_id,
                    span_type=JunjoOtelSpanTypes.NODE,
                    parent_definition_id=parent_definition_id,
                    store_id=store_id,
                ),
            )
        )

    def node_completed(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        parent_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
    ) -> PreparedHookEvent | None:
        if self._hooks is None:
            return None
        return PreparedHookEvent(
            "node_completed",
            hook_events.NodeCompletedEvent(
                run_id=run_id,
                definition_id=definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                span_type=JunjoOtelSpanTypes.NODE,
                parent_definition_id=parent_definition_id,
                store_id=store_id,
            ),
        )

    def node_failed(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        parent_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        error: Exception,
    ) -> PreparedHookEvent | None:
        if self._hooks is None:
            return None
        return PreparedHookEvent(
            "node_failed",
            hook_events.NodeFailedEvent(
                run_id=run_id,
                definition_id=definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                span_type=JunjoOtelSpanTypes.NODE,
                parent_definition_id=parent_definition_id,
                store_id=store_id,
                error=error,
            ),
        )

    def node_cancelled(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        parent_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        reason: str,
    ) -> PreparedHookEvent | None:
        if self._hooks is None:
            return None
        return PreparedHookEvent(
            "node_cancelled",
            hook_events.NodeCancelledEvent(
                run_id=run_id,
                definition_id=definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                span_type=JunjoOtelSpanTypes.NODE,
                parent_definition_id=parent_definition_id,
                store_id=store_id,
                reason=reason,
            ),
        )

    async def run_concurrent_started(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        parent_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
    ) -> None:
        await self.dispatch(
            PreparedHookEvent(
                "run_concurrent_started",
                hook_events.RunConcurrentStartedEvent(
                    run_id=run_id,
                    definition_id=definition_id,
                    name=name,
                    trace_id=trace_id,
                    span_id=span_id,
                    span_type=JunjoOtelSpanTypes.RUN_CONCURRENT,
                    parent_definition_id=parent_definition_id,
                    store_id=store_id,
                ),
            )
        )

    def run_concurrent_completed(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        parent_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
    ) -> PreparedHookEvent | None:
        if self._hooks is None:
            return None
        return PreparedHookEvent(
            "run_concurrent_completed",
            hook_events.RunConcurrentCompletedEvent(
                run_id=run_id,
                definition_id=definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                span_type=JunjoOtelSpanTypes.RUN_CONCURRENT,
                parent_definition_id=parent_definition_id,
                store_id=store_id,
            ),
        )

    def run_concurrent_failed(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        parent_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        error: Exception,
    ) -> PreparedHookEvent | None:
        if self._hooks is None:
            return None
        return PreparedHookEvent(
            "run_concurrent_failed",
            hook_events.RunConcurrentFailedEvent(
                run_id=run_id,
                definition_id=definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                span_type=JunjoOtelSpanTypes.RUN_CONCURRENT,
                parent_definition_id=parent_definition_id,
                store_id=store_id,
                error=error,
            ),
        )

    def run_concurrent_cancelled(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        parent_definition_id: str,
        store_id: str,
        trace_id: str,
        span_id: str,
        reason: str,
    ) -> PreparedHookEvent | None:
        if self._hooks is None:
            return None
        return PreparedHookEvent(
            "run_concurrent_cancelled",
            hook_events.RunConcurrentCancelledEvent(
                run_id=run_id,
                definition_id=definition_id,
                name=name,
                trace_id=trace_id,
                span_id=span_id,
                span_type=JunjoOtelSpanTypes.RUN_CONCURRENT,
                parent_definition_id=parent_definition_id,
                store_id=store_id,
                reason=reason,
            ),
        )

    async def state_changed(
        self,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        span_type: JunjoOtelSpanTypes,
        store_id: str,
        store_name: str,
        action_name: str,
        patch: str,
        state: StateT,
        parent_definition_id: str,
        trace_id: str,
        span_id: str,
    ) -> None:
        await self.dispatch(
            PreparedHookEvent(
                "state_changed",
                hook_events.StateChangedEvent(
                    run_id=run_id,
                    definition_id=definition_id,
                    name=name,
                    trace_id=trace_id,
                    span_id=span_id,
                    span_type=span_type,
                    store_id=store_id,
                    store_name=store_name,
                    action_name=action_name,
                    patch=patch,
                    state=state,
                    parent_definition_id=parent_definition_id,
                ),
            )
        )

    def _record_hook_error(
        self,
        event_name: str,
        callback,
        exc: Exception,
        event: hook_events.LifecycleEvent,
    ) -> None:
        tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)
        callback_name = getattr(callback, "__qualname__", callback.__class__.__qualname__)
        callback_module = getattr(callback, "__module__", callback.__class__.__module__)

        with tracer.start_as_current_span("junjo.hook_error") as span:
            span.set_attribute("junjo.hook.event", event_name)
            span.set_attribute(
                "junjo.hook.callback",
                f"{callback_module}.{callback_name}",
            )
            span.set_attribute("junjo.hook.error.type", type(exc).__name__)
            span.set_attribute("junjo.hook.error.message", str(exc))
            span.set_attribute("junjo.trace_id", event.trace_id)
            span.set_attribute("junjo.span_id", event.span_id)
            span.set_attribute("junjo.run_id", event.run_id)
            span.set_attribute("junjo.definition_id", event.definition_id)
            span.set_status(trace.StatusCode.ERROR, str(exc))
            span.record_exception(exc)
