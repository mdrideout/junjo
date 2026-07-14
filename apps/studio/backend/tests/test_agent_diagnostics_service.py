"""Application-service filtering tests for Agent semantic list queries."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.features.agent_diagnostics import service
from app.features.agent_diagnostics.schemas import AgentExecutionSummary

PROJECTION_PATH = Path(__file__).parent / "generated" / "agent_semantic_projections.json"


def _summary() -> AgentExecutionSummary:
    projection = json.loads(PROJECTION_PATH.read_text())[0]
    return AgentExecutionSummary.model_validate_json(json.dumps(projection["summary"]))


@pytest.mark.asyncio
async def test_list_filters_use_inclusive_aware_execution_bounds_without_prefetch_cap() -> None:
    summary = _summary()
    assert summary.start_time.tzinfo is not None
    assert summary.end_time.tzinfo is not None
    owner_span = {
        "owner": True,
        "resource_attributes_json": {
            "service.namespace": summary.service.namespace,
            "service.name": summary.service.name,
        },
    }
    with (
        patch(
            "app.features.agent_diagnostics.repository.list_agent_owner_spans",
            new=AsyncMock(return_value=[owner_span]),
        ) as repository_query,
        patch(
            "app.features.agent_diagnostics.service.assemble_agent_summary",
            return_value=summary,
        ),
    ):
        excluded_by_start = await service.list_agent_executions(
            service_namespace=summary.service.namespace,
            service_name=summary.service.name,
            agent_key=None,
            structural_id=None,
            service_version=None,
            outcome=None,
            start_time=summary.start_time + timedelta(microseconds=1),
            end_time=None,
            limit=1,
        )
        excluded_by_end = await service.list_agent_executions(
            service_namespace=summary.service.namespace,
            service_name=summary.service.name,
            agent_key=None,
            structural_id=None,
            service_version=None,
            outcome=None,
            start_time=None,
            end_time=summary.end_time - timedelta(microseconds=1),
            limit=1,
        )
        included = await service.list_agent_executions(
            service_namespace=summary.service.namespace,
            service_name=summary.service.name,
            agent_key=None,
            structural_id=None,
            service_version=None,
            outcome=None,
            start_time=summary.start_time,
            end_time=summary.end_time,
            limit=1,
        )
    assert excluded_by_start == []
    assert excluded_by_end == []
    assert included == [summary]
    assert repository_query.await_args_list[0].args == (summary.service.name,)
    assert repository_query.await_args_list[0].kwargs == {}
