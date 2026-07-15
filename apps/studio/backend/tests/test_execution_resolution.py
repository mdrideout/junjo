"""Exact authenticated execution resolution tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.features.auth.dependencies import get_authenticated_user
from app.features.execution_resolution import service
from app.features.execution_resolution.contract import ExecutionResolutionConflictError
from app.features.execution_resolution.schemas import ExecutionResolution
from app.main import app

TRACE_ID = "1" * 32
SPAN_ID = "a" * 16


def _owner(
    *,
    namespace: str = "junjo.examples",
    name: str = "ai-chat",
    executable_type: str = "workflow",
    runtime_id: str = "workflow-run",
    span_id: str = SPAN_ID,
) -> dict:
    return {
        "trace_id": TRACE_ID,
        "span_id": span_id,
        "attributes_json": {
            "junjo.telemetry.contract_version": 2,
            "junjo.span_type": executable_type,
            "junjo.executable_runtime_id": runtime_id,
        },
        "resource_attributes_json": {
            "service.namespace": namespace,
            "service.name": name,
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("executable_type", "expected_detail"),
    [
        ("workflow", f"/workflows/ai-chat/{TRACE_ID}/{SPAN_ID}"),
        ("subflow", f"/workflows/ai-chat/{TRACE_ID}/{SPAN_ID}"),
        ("agent", f"/agents/{TRACE_ID}/{SPAN_ID}"),
    ],
)
async def test_service_resolves_exact_owner_and_builds_existing_destinations(
    executable_type: str,
    expected_detail: str,
) -> None:
    with patch(
        "app.features.execution_resolution.repository.list_owner_candidates",
        new=AsyncMock(return_value=[_owner(executable_type=executable_type)]),
    ):
        resolved = await service.resolve_execution(
            service_namespace="junjo.examples",
            service_name="ai-chat",
            executable_type=executable_type,
            runtime_id="workflow-run",
        )

    assert resolved is not None
    assert resolved.detail_path == expected_detail
    assert resolved.trace_path == f"/traces/ai-chat/{TRACE_ID}/{SPAN_ID}"


@pytest.mark.asyncio
async def test_service_filters_physical_candidates_by_complete_semantic_scope() -> None:
    candidates = [
        _owner(namespace="wrong"),
        _owner(name="wrong"),
        _owner(runtime_id="wrong"),
        _owner(executable_type="agent"),
    ]
    with patch(
        "app.features.execution_resolution.repository.list_owner_candidates",
        new=AsyncMock(return_value=candidates),
    ):
        resolved = await service.resolve_execution(
            service_namespace="junjo.examples",
            service_name="ai-chat",
            executable_type="workflow",
            runtime_id="workflow-run",
        )

    assert resolved is None


@pytest.mark.asyncio
async def test_service_rejects_ambiguous_exact_identity() -> None:
    with patch(
        "app.features.execution_resolution.repository.list_owner_candidates",
        new=AsyncMock(return_value=[_owner(), _owner(span_id="b" * 16)]),
    ):
        with pytest.raises(ExecutionResolutionConflictError) as raised:
            await service.resolve_execution(
                service_namespace="junjo.examples",
                service_name="ai-chat",
                executable_type="workflow",
                runtime_id="workflow-run",
            )

    assert raised.value.match_count == 2


@pytest.fixture
def authenticated_app(mock_authenticated_user):
    app.dependency_overrides[get_authenticated_user] = lambda: mock_authenticated_user
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_authenticated_user, None)


@pytest.mark.asyncio
async def test_route_requires_an_authenticated_studio_session() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/execution-resolution",
            params={
                "service_namespace": "junjo.examples",
                "service_name": "ai-chat",
                "executable_type": "workflow",
                "runtime_id": "workflow-run",
            },
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_route_returns_typed_resolution(authenticated_app) -> None:
    resolved = ExecutionResolution(
        service_namespace="junjo.examples",
        service_name="ai-chat",
        executable_type="workflow",
        runtime_id="workflow-run",
        trace_id=TRACE_ID,
        span_id=SPAN_ID,
        detail_path=f"/workflows/ai-chat/{TRACE_ID}/{SPAN_ID}",
        trace_path=f"/traces/ai-chat/{TRACE_ID}/{SPAN_ID}",
    )
    with patch(
        "app.features.execution_resolution.service.resolve_execution",
        new=AsyncMock(return_value=resolved),
    ):
        transport = ASGITransport(app=authenticated_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/execution-resolution",
                params={
                    "service_namespace": "junjo.examples",
                    "service_name": "ai-chat",
                    "executable_type": "workflow",
                    "runtime_id": "workflow-run",
                },
            )

    assert response.status_code == 200
    assert response.json() == resolved.model_dump(mode="json")


@pytest.mark.asyncio
async def test_route_exposes_conflict_without_selecting_a_match(authenticated_app) -> None:
    with patch(
        "app.features.execution_resolution.service.resolve_execution",
        new=AsyncMock(side_effect=ExecutionResolutionConflictError(2)),
    ):
        transport = ASGITransport(app=authenticated_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/execution-resolution",
                params={
                    "service_namespace": "",
                    "service_name": "ai-chat",
                    "executable_type": "agent",
                    "runtime_id": "agent-run",
                },
            )

    assert response.status_code == 409
    assert response.json() == {
        "code": "ambiguous_execution_identity",
        "message": "Execution identity resolved to multiple owner spans.",
        "match_count": 2,
    }
