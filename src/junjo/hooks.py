from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from .state import BaseState
from .telemetry.otel_schema import JunjoOtelSpanTypes

if TYPE_CHECKING:
    from .workflow import ExecutionResult


StateT = TypeVar("StateT", bound=BaseState)
HookEventT = TypeVar("HookEventT")
HookCallback = Callable[[HookEventT], None | Awaitable[None]]


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    """Base payload shared by every public hook event."""

    run_id: str
    executable_definition_id: str
    name: str
    trace_id: str
    span_id: str
    span_type: JunjoOtelSpanTypes
    executable_runtime_id: str
    executable_structural_id: str
    enclosing_graph_structural_id: str
    parent_executable_runtime_id: str | None
    parent_executable_structural_id: str | None

    @property
    def hook_name(self) -> str:
        """
        Return the public lifecycle hook name for this payload.

        This is derived from the concrete event class name so callers can log
        the event type directly without each payload redefining its own string
        constant.
        """
        class_name = type(self).__name__
        stem = class_name[:-5] if class_name.endswith("Event") else class_name

        hook_name: list[str] = []
        for index, char in enumerate(stem):
            if char.isupper() and index > 0:
                previous = stem[index - 1]
                next_char = stem[index + 1] if index + 1 < len(stem) else ""
                if previous.islower() or (previous.isupper() and next_char.islower()):
                    hook_name.append("_")
            hook_name.append(char.lower())

        return "".join(hook_name)


@dataclass(frozen=True, slots=True)
class WorkflowStartedEvent(LifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_workflow_started` callbacks."""

    store_id: str
    graph_json: str


@dataclass(frozen=True, slots=True)
class WorkflowCompletedEvent(LifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_workflow_completed` callbacks."""

    result: ExecutionResult[StateT]
    store_id: str


@dataclass(frozen=True, slots=True)
class WorkflowFailedEvent(LifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_workflow_failed` callbacks."""

    error: Exception
    state: StateT
    store_id: str


@dataclass(frozen=True, slots=True)
class WorkflowCancelledEvent(LifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_workflow_cancelled` callbacks."""

    reason: str
    state: StateT
    store_id: str


@dataclass(frozen=True, slots=True)
class SubflowStartedEvent(LifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_subflow_started` callbacks."""

    store_id: str
    graph_json: str


@dataclass(frozen=True, slots=True)
class SubflowCompletedEvent(LifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_subflow_completed` callbacks."""

    result: ExecutionResult[StateT]
    store_id: str


@dataclass(frozen=True, slots=True)
class SubflowFailedEvent(LifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_subflow_failed` callbacks."""

    error: Exception
    state: StateT
    store_id: str


@dataclass(frozen=True, slots=True)
class SubflowCancelledEvent(LifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_subflow_cancelled` callbacks."""

    reason: str
    state: StateT
    store_id: str


@dataclass(frozen=True, slots=True)
class NodeStartedEvent(LifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_node_started` callbacks."""

    parent_executable_definition_id: str
    store_id: str


@dataclass(frozen=True, slots=True)
class NodeCompletedEvent(LifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_node_completed` callbacks."""

    parent_executable_definition_id: str
    store_id: str


@dataclass(frozen=True, slots=True)
class NodeFailedEvent(LifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_node_failed` callbacks."""

    parent_executable_definition_id: str
    store_id: str
    error: Exception


@dataclass(frozen=True, slots=True)
class NodeCancelledEvent(LifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_node_cancelled` callbacks."""

    parent_executable_definition_id: str
    store_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class RunConcurrentStartedEvent(LifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_run_concurrent_started` callbacks."""

    parent_executable_definition_id: str
    store_id: str


@dataclass(frozen=True, slots=True)
class RunConcurrentCompletedEvent(LifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_run_concurrent_completed` callbacks."""

    parent_executable_definition_id: str
    store_id: str


@dataclass(frozen=True, slots=True)
class RunConcurrentFailedEvent(LifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_run_concurrent_failed` callbacks."""

    parent_executable_definition_id: str
    store_id: str
    error: Exception


@dataclass(frozen=True, slots=True)
class RunConcurrentCancelledEvent(LifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_run_concurrent_cancelled` callbacks."""

    parent_executable_definition_id: str
    store_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class StateChangedEvent(LifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_state_changed` callbacks."""

    store_id: str
    store_name: str
    action_name: str
    patch: str
    state: StateT
    parent_executable_definition_id: str


class Hooks:
    """
    Registry for optional Junjo lifecycle callbacks.

    Hooks are observers. They do not create spans or control workflow execution.
    To use them, register one or more callbacks and pass the registry to a
    workflow or subflow.

    .. rubric:: Example

    .. code-block:: python

        hooks = Hooks()

        def log_completed(event: WorkflowCompletedEvent[MyState]) -> None:
            print(event.hook_name, event.result.state.model_dump())

        hooks.on_workflow_completed(log_completed)

        workflow = Workflow(..., hooks=hooks)
    """

    def __init__(self) -> None:
        self._callbacks: dict[str, list[HookCallback[Any]]] = defaultdict(list)

    def _register(
        self,
        event_name: str,
        callback: HookCallback[Any],
    ) -> Callable[[], None]:
        self._callbacks[event_name].append(callback)

        def unsubscribe() -> None:
            callbacks = self._callbacks.get(event_name)
            if callbacks is None:
                return
            if callback in callbacks:
                callbacks.remove(callback)

        return unsubscribe

    def _callbacks_for(self, event_name: str) -> tuple[HookCallback[Any], ...]:
        return tuple(self._callbacks.get(event_name, ()))

    def on_workflow_started(
        self, callback: HookCallback[WorkflowStartedEvent]
    ) -> Callable[[], None]:
        """Register a callback for the start of a top-level workflow run."""

        return self._register("workflow_started", callback)

    def on_workflow_completed(
        self, callback: HookCallback[WorkflowCompletedEvent[StateT]]
    ) -> Callable[[], None]:
        """Register a callback for successful workflow completion."""

        return self._register(
            "workflow_completed",
            cast(HookCallback[Any], callback),
        )

    def on_workflow_failed(
        self, callback: HookCallback[WorkflowFailedEvent[StateT]]
    ) -> Callable[[], None]:
        """Register a callback for workflow failures."""

        return self._register("workflow_failed", cast(HookCallback[Any], callback))

    def on_workflow_cancelled(
        self, callback: HookCallback[WorkflowCancelledEvent[StateT]]
    ) -> Callable[[], None]:
        """Register a callback for workflow cancellation."""

        return self._register(
            "workflow_cancelled",
            cast(HookCallback[Any], callback),
        )

    def on_subflow_started(
        self, callback: HookCallback[SubflowStartedEvent]
    ) -> Callable[[], None]:
        """Register a callback for subflow start events."""

        return self._register("subflow_started", callback)

    def on_subflow_completed(
        self, callback: HookCallback[SubflowCompletedEvent[StateT]]
    ) -> Callable[[], None]:
        """Register a callback for successful subflow completion."""

        return self._register(
            "subflow_completed",
            cast(HookCallback[Any], callback),
        )

    def on_subflow_failed(
        self, callback: HookCallback[SubflowFailedEvent[StateT]]
    ) -> Callable[[], None]:
        """Register a callback for subflow failures."""

        return self._register("subflow_failed", cast(HookCallback[Any], callback))

    def on_subflow_cancelled(
        self, callback: HookCallback[SubflowCancelledEvent[StateT]]
    ) -> Callable[[], None]:
        """Register a callback for subflow cancellation."""

        return self._register(
            "subflow_cancelled",
            cast(HookCallback[Any], callback),
        )

    def on_node_started(
        self, callback: HookCallback[NodeStartedEvent]
    ) -> Callable[[], None]:
        """Register a callback for node start events."""

        return self._register("node_started", callback)

    def on_node_completed(
        self, callback: HookCallback[NodeCompletedEvent]
    ) -> Callable[[], None]:
        """Register a callback for successful node completion."""

        return self._register("node_completed", callback)

    def on_node_failed(
        self, callback: HookCallback[NodeFailedEvent]
    ) -> Callable[[], None]:
        """Register a callback for node failures."""

        return self._register("node_failed", callback)

    def on_node_cancelled(
        self, callback: HookCallback[NodeCancelledEvent]
    ) -> Callable[[], None]:
        """Register a callback for node cancellation."""

        return self._register("node_cancelled", callback)

    def on_run_concurrent_started(
        self, callback: HookCallback[RunConcurrentStartedEvent]
    ) -> Callable[[], None]:
        """Register a callback for `RunConcurrent` start events."""

        return self._register("run_concurrent_started", callback)

    def on_run_concurrent_completed(
        self, callback: HookCallback[RunConcurrentCompletedEvent]
    ) -> Callable[[], None]:
        """Register a callback for successful `RunConcurrent` completion."""

        return self._register("run_concurrent_completed", callback)

    def on_run_concurrent_failed(
        self, callback: HookCallback[RunConcurrentFailedEvent]
    ) -> Callable[[], None]:
        """Register a callback for `RunConcurrent` failures."""

        return self._register("run_concurrent_failed", callback)

    def on_run_concurrent_cancelled(
        self, callback: HookCallback[RunConcurrentCancelledEvent]
    ) -> Callable[[], None]:
        """Register a callback for `RunConcurrent` cancellation."""

        return self._register("run_concurrent_cancelled", callback)

    def on_state_changed(
        self, callback: HookCallback[StateChangedEvent[StateT]]
    ) -> Callable[[], None]:
        """Register a callback for committed state updates."""

        return self._register("state_changed", cast(HookCallback[Any], callback))


__all__ = [
    "Hooks",
    "LifecycleEvent",
    "WorkflowStartedEvent",
    "WorkflowCompletedEvent",
    "WorkflowFailedEvent",
    "WorkflowCancelledEvent",
    "SubflowStartedEvent",
    "SubflowCompletedEvent",
    "SubflowFailedEvent",
    "SubflowCancelledEvent",
    "NodeStartedEvent",
    "NodeCompletedEvent",
    "NodeFailedEvent",
    "NodeCancelledEvent",
    "RunConcurrentStartedEvent",
    "RunConcurrentCompletedEvent",
    "RunConcurrentFailedEvent",
    "RunConcurrentCancelledEvent",
    "StateChangedEvent",
]
