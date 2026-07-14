"""HTTP contract tests for Agent execution summary queries."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.features.agent_diagnostics.schemas import AgentExecutionSummary
from app.features.auth.dependencies import get_authenticated_user
from app.main import app

PROJECTION_PATH = Path(__file__).parent / "generated" / "agent_semantic_projections.json"


def _summary() -> AgentExecutionSummary:
    projection = json.loads(PROJECTION_PATH.read_text())[0]
    return AgentExecutionSummary.model_validate_json(json.dumps(projection["summary"]))


def test_agent_list_openapi_separates_transport_and_semantic_errors() -> None:
    responses = app.openapi()["paths"]["/api/v1/agent-executions"]["get"]["responses"]
    assert responses["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AgentEvidenceErrorResponse"
    }
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HTTPValidationError"
    }


@pytest.fixture
def authenticated_app(mock_authenticated_user):
    app.dependency_overrides[get_authenticated_user] = lambda: mock_authenticated_user
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_authenticated_user, None)


@pytest.mark.asyncio
async def test_agent_list_requires_authentication() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/agent-executions?service_namespace=&service_name=example"
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_agent_executions_route_returns_typed_summary(authenticated_app) -> None:
    summary = _summary()
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.service.list_agent_executions",
        new=AsyncMock(return_value=[summary]),
    ) as query:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/agent-executions",
                params={"service_namespace": "", "service_name": summary.service.name},
            )
    assert response.status_code == 200
    assert response.json() == [summary.model_dump(mode="json")]
    assert query.await_args.kwargs["service_namespace"] == ""
    assert query.await_args.kwargs["service_name"] == summary.service.name


@pytest.mark.asyncio
async def test_list_agent_executions_requires_explicit_service_scope(authenticated_app) -> None:
    transport = ASGITransport(app=authenticated_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/agent-executions",
            params={"service_name": "example"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"start_time": "2026-07-14T12:00:00"},
        {
            "start_time": "2026-07-14T12:00:01Z",
            "end_time": "2026-07-14T12:00:00Z",
        },
    ],
    ids=["naive-time", "inverted-range"],
)
async def test_list_agent_executions_rejects_invalid_time_boundaries(
    authenticated_app,
    params: dict[str, str],
) -> None:
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.service.list_agent_executions",
        new=AsyncMock(return_value=[]),
    ) as query:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/agent-executions",
                params={
                    "service_namespace": "",
                    "service_name": "example",
                    **params,
                },
            )

    assert response.status_code == 422
    assert response.json()["detail"]
    query.assert_not_awaited()
