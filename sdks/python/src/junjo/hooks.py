from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from ._identity import ExecutableType
from .state import BaseState

if TYPE_CHECKING:
    from .agent import state as agent_state
    from .agent.errors import AgentExecutionError
    from .agent.result import AgentExecutionResult
    from .workflow import ExecutionResult


StateT = TypeVar("StateT", bound=BaseState)
HookEventT = TypeVar("HookEventT")
HookCallback = Callable[[HookEventT], None | Awaitable[None]]


@dataclass(frozen=True, slots=True, kw_only=True)
class LifecycleEvent:
    """Base payload shared by every public hook event."""

    run_id: str
    executable_definition_id: str
    name: str
    trace_id: str
    span_id: str
    executable_type: ExecutableType
    executable_runtime_id: str
    executable_structural_id: str
    parent_executable_definition_id: str | None = None
    parent_executable_runtime_id: str | None = None
    parent_executable_structural_id: str | None = None
    parent_executable_type: ExecutableType | None = None

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


@dataclass(frozen=True, slots=True, kw_only=True)
class GraphLifecycleEvent(LifecycleEvent):
    """Lifecycle payload for an executable that belongs to a compiled Graph."""

    enclosing_graph_structural_id: str


@dataclass(frozen=True, slots=True)
class WorkflowStartedEvent(GraphLifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_workflow_started` callbacks."""

    store_id: str
    graph_json: str


@dataclass(frozen=True, slots=True)
class WorkflowCompletedEvent(GraphLifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_workflow_completed` callbacks."""

    result: ExecutionResult[StateT]
    store_id: str


@dataclass(frozen=True, slots=True)
class WorkflowFailedEvent(GraphLifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_workflow_failed` callbacks."""

    error: Exception
    state: StateT
    store_id: str


@dataclass(frozen=True, slots=True)
class WorkflowCancelledEvent(GraphLifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_workflow_cancelled` callbacks."""

    reason: str
    state: StateT
    store_id: str


@dataclass(frozen=True, slots=True)
class SubflowStartedEvent(GraphLifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_subflow_started` callbacks."""

    store_id: str
    graph_json: str


@dataclass(frozen=True, slots=True)
class SubflowCompletedEvent(GraphLifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_subflow_completed` callbacks."""

    result: ExecutionResult[StateT]
    store_id: str


@dataclass(frozen=True, slots=True)
class SubflowFailedEvent(GraphLifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_subflow_failed` callbacks."""

    error: Exception
    state: StateT
    store_id: str


@dataclass(frozen=True, slots=True)
class SubflowCancelledEvent(GraphLifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_subflow_cancelled` callbacks."""

    reason: str
    state: StateT
    store_id: str


@dataclass(frozen=True, slots=True)
class NodeStartedEvent(GraphLifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_node_started` callbacks."""

    store_id: str


@dataclass(frozen=True, slots=True)
class NodeCompletedEvent(GraphLifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_node_completed` callbacks."""

    store_id: str


@dataclass(frozen=True, slots=True)
class NodeFailedEvent(GraphLifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_node_failed` callbacks."""

    store_id: str
    error: Exception


@dataclass(frozen=True, slots=True)
class NodeCancelledEvent(GraphLifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_node_cancelled` callbacks."""

    store_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class RunConcurrentStartedEvent(GraphLifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_run_concurrent_started` callbacks."""

    store_id: str


@dataclass(frozen=True, slots=True)
class RunConcurrentCompletedEvent(GraphLifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_run_concurrent_completed` callbacks."""

    store_id: str


@dataclass(frozen=True, slots=True)
class RunConcurrentFailedEvent(GraphLifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_run_concurrent_failed` callbacks."""

    store_id: str
    error: Exception


@dataclass(frozen=True, slots=True)
class RunConcurrentCancelledEvent(GraphLifecycleEvent):
    """Payload delivered to :meth:`junjo.Hooks.on_run_concurrent_cancelled` callbacks."""

    store_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class StateChangedEvent(GraphLifecycleEvent, Generic[StateT]):
    """Payload delivered to :meth:`junjo.Hooks.on_state_changed` callbacks."""

    store_id: str
    store_name: str
    action_name: str
    patch: str
    state: StateT


@dataclass(frozen=True, slots=True)
class AgentStartedEvent(LifecycleEvent):
    """Payload delivered after an Agent invocation is admitted."""

    agent_key: str
    store_id: str


@dataclass(frozen=True, slots=True)
class AgentCompletedEvent(LifecycleEvent):
    """Payload delivered after an Agent commits a successful result."""

    agent_key: str
    store_id: str
    result: AgentExecutionResult[Any]


@dataclass(frozen=True, slots=True)
class AgentFailedEvent(LifecycleEvent):
    """Payload delivered after an admitted Agent execution fails."""

    agent_key: str
    store_id: str
    error: AgentExecutionError
    state: agent_state.AgentStateSnapshot


@dataclass(frozen=True, slots=True)
class AgentCancelledEvent(LifecycleEvent):
    """Payload delivered after an admitted Agent execution is cancelled."""

    agent_key: str
    store_id: str
    reason: str
    state: agent_state.AgentStateSnapshot


class Hooks:
    """
    Registry for optional Junjo lifecycle callbacks.

    Hooks are observers. They do not create spans or control Workflow or Agent
    execution.
    If a hook callback raises, Junjo keeps execution isolated and continues
    dispatching the remaining callbacks for that hook.

    To use them, register one or more callbacks and pass the registry to a
    Workflow, Subflow, or Agent definition.

    Every ``on_*`` registration method returns an unsubscribe callback. Call
    the returned function when the callback should no longer receive events.

    .. rubric:: Example

    .. code-block:: python

        import logging

        hooks = Hooks()
        logger = logging.getLogger(__name__)

        def log_completed(event: WorkflowCompletedEvent[MyState]) -> None:
            logger.info("%s %s", event.hook_name, event.result.state.model_dump())

        unsubscribe = hooks.on_workflow_completed(log_completed)

        workflow = Workflow(..., hooks=hooks)

        # Later, if this callback should no longer run:
        unsubscribe()
    """

    def __init__(self) -> None:
        self._callbacks: dict[str, list[HookCallback[Any]]] = defaultdict(list)
        self._lock = RLock()

    def _register(
        self,
        event_name: str,
        callback: HookCallback[Any],
    ) -> Callable[[], None]:
        with self._lock:
            self._callbacks[event_name].append(callback)

        def unsubscribe() -> None:
            with self._lock:
                callbacks = self._callbacks.get(event_name)
                if callbacks is None:
                    return
                if callback in callbacks:
                    callbacks.remove(callback)

        return unsubscribe

    def _callbacks_for(self, event_name: str) -> tuple[HookCallback[Any], ...]:
        with self._lock:
            return tuple(self._callbacks.get(event_name, ()))

    def _snapshot(self) -> dict[str, tuple[HookCallback[Any], ...]]:
        """Copy callback membership once for one admitted execution."""

        with self._lock:
            return {
                event_name: tuple(callbacks)
                for event_name, callbacks in self._callbacks.items()
            }

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

    def on_agent_started(
        self, callback: HookCallback[AgentStartedEvent]
    ) -> Callable[[], None]:
        """Register a callback for admitted Agent execution start."""

        return self._register("agent_started", callback)

    def on_agent_completed(
        self, callback: HookCallback[AgentCompletedEvent]
    ) -> Callable[[], None]:
        """Register a callback for successful Agent completion."""

        return self._register("agent_completed", callback)

    def on_agent_failed(
        self, callback: HookCallback[AgentFailedEvent]
    ) -> Callable[[], None]:
        """Register a callback for admitted Agent execution failure."""

        return self._register("agent_failed", callback)

    def on_agent_cancelled(
        self, callback: HookCallback[AgentCancelledEvent]
    ) -> Callable[[], None]:
        """Register a callback for admitted Agent execution cancellation."""

        return self._register("agent_cancelled", callback)


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
    "AgentStartedEvent",
    "AgentCompletedEvent",
    "AgentFailedEvent",
    "AgentCancelledEvent",
]
