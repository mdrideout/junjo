"""Semantic interpretation for exact execution identity resolution."""

from __future__ import annotations

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
    detail_path = (
        f"/agents/{trace_id}/{span_id}"
        if executable_type == "agent"
        else f"/workflows/{encoded_service_name}/{trace_id}/{span_id}"
    )
    return ExecutionResolution(
        service_namespace=service_namespace,
        service_name=service_name,
        executable_type=executable_type,
        runtime_id=runtime_id,
        trace_id=trace_id,
        span_id=span_id,
        detail_path=detail_path,
        trace_path=f"/traces/{encoded_service_name}/{trace_id}/{span_id}",
    )
