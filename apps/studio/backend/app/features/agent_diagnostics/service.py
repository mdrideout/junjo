"""Application service for semantic Agent execution queries."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.features.agent_diagnostics import repository
from app.features.agent_diagnostics.assembler import (
    assemble_agent_summary,
)
from app.features.agent_diagnostics.schemas import (
    AgentExecutionSummary,
)


async def list_agent_executions(
    *,
    service_namespace: str,
    service_name: str,
    agent_key: str | None,
    structural_id: str | None,
    service_version: str | None,
    outcome: Literal["completed", "failed", "cancelled"] | None,
    start_time: datetime | None,
    end_time: datetime | None,
    limit: int,
) -> list[AgentExecutionSummary]:
    """Return service-scoped Agent summaries after semantic validation."""
    owner_spans = await repository.list_agent_owner_spans(service_name)
    summaries: list[AgentExecutionSummary] = []
    for owner_span in owner_spans:
        resource = owner_span.get("resource_attributes_json")
        if not isinstance(resource, dict):
            continue
        if resource.get("service.name") != service_name:
            continue
        if resource.get("service.namespace", "") != service_namespace:
            continue
        summary = assemble_agent_summary(owner_span)
        if summary.service.namespace != service_namespace or summary.service.name != service_name:
            continue
        if agent_key is not None and summary.agent_key != agent_key:
            continue
        if structural_id is not None and summary.structural_id != structural_id:
            continue
        if service_version is not None and summary.service.version != service_version:
            continue
        if outcome is not None and summary.outcome != outcome:
            continue
        if start_time is not None and summary.start_time < start_time:
            continue
        if end_time is not None and summary.end_time > end_time:
            continue
        summaries.append(summary)
    return sorted(summaries, key=lambda item: item.start_time, reverse=True)[:limit]
