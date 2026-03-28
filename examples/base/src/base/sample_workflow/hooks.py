from __future__ import annotations

from junjo import Hooks
from junjo.hooks import (
    LifecycleEvent,
    StateChangedEvent,
    SubflowCompletedEvent,
    WorkflowCompletedEvent,
)

from base.sample_workflow.sample_subflow.store import SampleSubflowState
from base.sample_workflow.store import SampleWorkflowState


def _base_event_details(event: LifecycleEvent) -> dict:
    details = {
        "hook_name": event.hook_name,
        "name": event.name,
        "run_id": event.run_id,
        "executable_definition_id": event.executable_definition_id,
        "executable_runtime_id": event.executable_runtime_id,
        "executable_structural_id": event.executable_structural_id,
        "enclosing_graph_structural_id": event.enclosing_graph_structural_id,
        "parent_executable_runtime_id": event.parent_executable_runtime_id,
        "parent_executable_structural_id": event.parent_executable_structural_id,
        "trace_id": event.trace_id,
        "span_id": event.span_id,
        "span_type": event.span_type,
    }
    return details


def _format_event_details(event: LifecycleEvent) -> dict:
    details = _base_event_details(event)
    for attribute in (
        "parent_executable_definition_id",
        "store_id",
        "graph_json",
        "patch",
        "action_name",
        "store_name",
        "reason",
    ):
        if hasattr(event, attribute):
            details[attribute] = getattr(event, attribute)

    if hasattr(event, "error"):
        details["error"] = repr(event.error)
    if hasattr(event, "state"):
        details["state"] = event.state.model_dump()
    if hasattr(event, "result"):
        details["result_state"] = event.result.state.model_dump()

    return details


def _log_event(event: LifecycleEvent) -> None:
    print(f"[hook] {event.hook_name}", _format_event_details(event))


def _log_workflow_completed(
    event: WorkflowCompletedEvent[SampleWorkflowState],
) -> None:
    state = event.result.state
    print(
        f"[hook] {event.hook_name}",
        {
            **_base_event_details(event),
            "counter": state.counter,
            "item_count": len(state.items),
            "joke": state.joke,
            "fact": state.fact,
        },
    )


def _log_subflow_completed(
    event: SubflowCompletedEvent[SampleSubflowState],
) -> None:
    state = event.result.state
    print(
        f"[hook] {event.hook_name}",
        {
            **_base_event_details(event),
            "item_count": len(state.items or []),
            "joke": state.joke,
            "fact": state.fact,
        },
    )


def _log_state_changed(event: StateChangedEvent[SampleWorkflowState]) -> None:
    state = event.state
    print(
        f"[hook] {event.hook_name}",
        {
            **_base_event_details(event),
            "action_name": event.action_name,
            "counter": state.counter,
            "item_count": len(state.items),
            "joke": state.joke,
            "fact": state.fact,
            "patch": event.patch,
        },
    )


def create_logging_hooks() -> Hooks:
    """
    Register one logging callback for every public hook type.

    The base example graph exercises workflow, run-concurrent, subflow, node,
    and state-changed hooks during a normal successful run.
    """
    hooks = Hooks()
    hooks.on_workflow_started(_log_event)
    hooks.on_workflow_completed(_log_workflow_completed)
    hooks.on_workflow_failed(_log_event)
    hooks.on_workflow_cancelled(_log_event)
    hooks.on_subflow_started(_log_event)
    hooks.on_subflow_completed(_log_subflow_completed)
    hooks.on_subflow_failed(_log_event)
    hooks.on_subflow_cancelled(_log_event)
    hooks.on_node_started(_log_event)
    hooks.on_node_completed(_log_event)
    hooks.on_node_failed(_log_event)
    hooks.on_node_cancelled(_log_event)
    hooks.on_run_concurrent_started(_log_event)
    hooks.on_run_concurrent_completed(_log_event)
    hooks.on_run_concurrent_failed(_log_event)
    hooks.on_run_concurrent_cancelled(_log_event)
    hooks.on_state_changed(_log_state_changed)
    return hooks
