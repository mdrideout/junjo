"""Semantic interpretation for exact execution identity resolution."""

from __future__ import annotations

import json
from urllib.parse import quote

from app.features.execution_resolution import repository
from app.features.execution_resolution.contract import ExecutionResolutionConflictError
from app.features.execution_resolution.schemas import (
    ExecutableType,
    ExecutionResolution,
)


async def resolve_execution(
    *,
    service_namespace: str,
    service_name: str,
    executable_type: ExecutableType,
    runtime_id: str,
) -> ExecutionResolution | None:
    """Resolve one active-contract owner span in an exact service scope."""
    candidates = await repository.list_owner_candidates(
        service_name=service_name,
        executable_type=executable_type,
        runtime_id=runtime_id,
    )
    matches: list[dict] = []
    for candidate in candidates:
        attributes = candidate.get("attributes_json")
        resource = candidate.get("resource_attributes_json")
        if not isinstance(attributes, dict) or not isinstance(resource, dict):
            continue
        if attributes.get("junjo.telemetry.contract_version") != 2:
            continue
        if attributes.get("junjo.span_type") != executable_type:
            continue
        if attributes.get("junjo.executable_runtime_id") != runtime_id:
            continue
        if resource.get("service.name") != service_name:
            continue
        if resource.get("service.namespace", "") != service_namespace:
            continue
        matches.append(candidate)

    if not matches:
        return None
    if len(matches) > 1:
        raise ExecutionResolutionConflictError(len(matches))

    match = matches[0]
    trace_id = match["trace_id"]
    span_id = match["span_id"]
    encoded_service_name = quote(service_name, safe="")
    if executable_type == "agent":
        detail_path = f"/agents/{trace_id}/{span_id}"
        failure_path = detail_path
    else:
        selected_span_id = await _single_graph_node_span_id(match)
        detail_path = f"/workflows/{encoded_service_name}/{trace_id}/{span_id}"
        if selected_span_id is not None:
            detail_path = f"{detail_path}/{selected_span_id}"
        failed_span_id = await _single_failed_graph_node_span_id(match)
        failure_path = f"/workflows/{encoded_service_name}/{trace_id}/{span_id}"
        if failed_span_id is not None:
            failure_path = f"{failure_path}/{failed_span_id}"
    return ExecutionResolution(
        service_namespace=service_namespace,
        service_name=service_name,
        executable_type=executable_type,
        runtime_id=runtime_id,
        trace_id=trace_id,
        span_id=span_id,
        detail_path=detail_path,
        failure_path=failure_path,
        trace_path=f"/traces/{encoded_service_name}/{trace_id}/{span_id}",
    )


async def _single_graph_node_span_id(owner: dict) -> str | None:
    """Select the one real Node in a one-Node Workflow without guessing by name."""

    attributes = owner.get("attributes_json")
    if not isinstance(attributes, dict):
        return None
    snapshot = attributes.get("junjo.workflow.execution_graph_snapshot")
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except json.JSONDecodeError:
            return None
    if not isinstance(snapshot, dict):
        return None
    nodes = snapshot.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 1:
        return None
    node = nodes[0]
    if not isinstance(node, dict):
        return None
    node_runtime_id = node.get("nodeRuntimeId")
    if not isinstance(node_runtime_id, str) or not node_runtime_id:
        return None

    trace_id = owner.get("trace_id")
    owner_span_id = owner.get("span_id")
    if not isinstance(trace_id, str) or not isinstance(owner_span_id, str):
        return None
    trace_spans = await repository.list_trace_spans(trace_id)
    matches = []
    for span in trace_spans:
        span_attributes = span.get("attributes_json")
        if (
            span.get("trace_id") == trace_id
            and span.get("parent_span_id") == owner_span_id
            and isinstance(span_attributes, dict)
            and span_attributes.get("junjo.telemetry.contract_version") == 2
            and span_attributes.get("junjo.span_type") == "node"
            and span_attributes.get("junjo.executable_runtime_id") == node_runtime_id
        ):
            matches.append(span)
    if len(matches) != 1:
        return None
    selected_span_id = matches[0].get("span_id")
    return selected_span_id if isinstance(selected_span_id, str) else None


async def _single_failed_graph_node_span_id(owner: dict) -> str | None:
    """Select one failed Node inside the resolved Workflow without guessing."""

    if not _has_failure_signal(owner):
        return None
    trace_id = owner.get("trace_id")
    owner_span_id = owner.get("span_id")
    if not isinstance(trace_id, str) or not isinstance(owner_span_id, str):
        return None

    trace_spans = await repository.list_trace_spans(trace_id)
    spans_by_id = {
        span_id: span for span in trace_spans if isinstance((span_id := span.get("span_id")), str)
    }
    matches = []
    for span in trace_spans:
        attributes = span.get("attributes_json")
        if (
            isinstance(attributes, dict)
            and attributes.get("junjo.telemetry.contract_version") == 2
            and attributes.get("junjo.span_type") == "node"
            and _has_failure_signal(span)
            and _is_descendant_of(span, owner_span_id, spans_by_id)
        ):
            matches.append(span)
    if len(matches) != 1:
        return None
    selected_span_id = matches[0].get("span_id")
    return selected_span_id if isinstance(selected_span_id, str) else None


def _has_failure_signal(span: dict) -> bool:
    attributes = span.get("attributes_json")
    if isinstance(attributes, dict) and attributes.get("error.type"):
        return True
    events = span.get("events_json")
    return isinstance(events, list) and any(
        isinstance(event, dict) and event.get("name") in {"exception", "junjo.hook_error"}
        for event in events
    )


def _is_descendant_of(span: dict, owner_span_id: str, spans_by_id: dict[str, dict]) -> bool:
    parent_span_id = span.get("parent_span_id")
    visited: set[str] = set()
    while isinstance(parent_span_id, str) and parent_span_id not in visited:
        if parent_span_id == owner_span_id:
            return True
        visited.add(parent_span_id)
        parent = spans_by_id.get(parent_span_id)
        if parent is None:
            return False
        parent_span_id = parent.get("parent_span_id")
    return False
