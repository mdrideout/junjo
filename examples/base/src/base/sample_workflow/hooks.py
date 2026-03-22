from __future__ import annotations

from junjo import Hooks


def _format_event_details(event) -> dict:
    details = {
        "name": event.name,
        "run_id": event.run_id,
        "definition_id": event.definition_id,
        "trace_id": event.trace_id,
        "span_id": event.span_id,
        "span_type": event.span_type,
    }

    for attribute in (
        "parent_definition_id",
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


def _log_event(event_name: str):
    def callback(event) -> None:
        print(f"[hook] {event_name}", _format_event_details(event))

    return callback


def create_logging_hooks() -> Hooks:
    """
    Register one logging callback for every public hook type.

    The base example graph exercises workflow, run-concurrent, subflow, node,
    and state-changed hooks during a normal successful run.
    """
    hooks = Hooks()
    hooks.on_workflow_started(_log_event("workflow_started"))
    hooks.on_workflow_completed(_log_event("workflow_completed"))
    hooks.on_workflow_failed(_log_event("workflow_failed"))
    hooks.on_workflow_cancelled(_log_event("workflow_cancelled"))
    hooks.on_subflow_started(_log_event("subflow_started"))
    hooks.on_subflow_completed(_log_event("subflow_completed"))
    hooks.on_subflow_failed(_log_event("subflow_failed"))
    hooks.on_subflow_cancelled(_log_event("subflow_cancelled"))
    hooks.on_node_started(_log_event("node_started"))
    hooks.on_node_completed(_log_event("node_completed"))
    hooks.on_node_failed(_log_event("node_failed"))
    hooks.on_node_cancelled(_log_event("node_cancelled"))
    hooks.on_run_concurrent_started(_log_event("run_concurrent_started"))
    hooks.on_run_concurrent_completed(_log_event("run_concurrent_completed"))
    hooks.on_run_concurrent_failed(_log_event("run_concurrent_failed"))
    hooks.on_run_concurrent_cancelled(_log_event("run_concurrent_cancelled"))
    hooks.on_state_changed(_log_event("state_changed"))
    return hooks
