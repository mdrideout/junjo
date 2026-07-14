"""HTTP contract tests for Agent semantic diagnostics."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.features.agent_diagnostics.contract import AgentEvidenceError, diagnostic
from app.features.agent_diagnostics.schemas import (
    AgentExecutionDetail,
    AgentExecutionSummary,
)
from app.features.auth.dependencies import get_authenticated_user
from app.main import app

PROJECTION_PATH = Path(__file__).parent / "generated" / "agent_semantic_projections.json"
AGENT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "telemetry"
    / "fixtures"
    / "agent"
    / "producer"
    / "direct_typed_completion.json"
)
MULTI_TOOL_FIXTURE_PATH = AGENT_FIXTURE_PATH.with_name("ordered_multiple_tools.json")
LIMIT_FIXTURE_PATH = AGENT_FIXTURE_PATH.with_name("over_budget_tool_batch.json")


def _projection() -> tuple[AgentExecutionSummary, AgentExecutionDetail]:
    projection = json.loads(PROJECTION_PATH.read_text())[0]
    return (
        AgentExecutionSummary.model_validate_json(json.dumps(projection["summary"])),
        AgentExecutionDetail.model_validate_json(json.dumps(projection["detail"])),
    )


def test_diagnostic_openapi_separates_transport_and_semantic_error_contracts() -> None:
    openapi = app.openapi()
    cases = (
        (
            "/api/v1/agent-executions",
            "#/components/schemas/AgentEvidenceErrorResponse",
        ),
        (
            "/api/v1/agent-executions/{trace_id}/{agent_span_id}",
            "#/components/schemas/AgentEvidenceErrorResponse",
        ),
        (
            "/api/v1/workflow-executions/{trace_id}/{workflow_span_id}/store",
            "#/components/schemas/WorkflowEvidenceErrorResponse",
        ),
    )
    for path, semantic_schema in cases:
        responses = openapi["paths"][path]["get"]["responses"]
        assert responses["409"]["content"]["application/json"]["schema"] == {
            "$ref": semantic_schema
        }
        assert responses["422"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/HTTPValidationError"
        }


@pytest.fixture
def authenticated_app(mock_authenticated_user):
    """Run one route test with an explicit authenticated Studio session dependency."""
    app.dependency_overrides[get_authenticated_user] = lambda: mock_authenticated_user
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_authenticated_user, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/agent-executions?service_namespace=&service_name=example",
        "/api/v1/agent-executions/11111111111111111111111111111111/aaaaaaaaaaaaaaaa",
    ],
)
async def test_agent_semantic_routes_require_authentication(path: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_agent_executions_route_returns_typed_summary(authenticated_app) -> None:
    summary, _ = _projection()
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
    body = response.json()
    assert isinstance(body.get("detail"), list)
    assert body["detail"]
    assert all(
        isinstance(issue.get("loc"), list)
        and issue["loc"][0] == "query"
        and isinstance(issue.get("msg"), str)
        and isinstance(issue.get("type"), str)
        for issue in body["detail"]
    )
    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_execution_detail_route_returns_typed_projection(authenticated_app) -> None:
    summary, detail = _projection()
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.service.get_agent_execution",
        new=AsyncMock(return_value=detail),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/agent-executions/{summary.trace_id}/{summary.agent_span_id}"
            )
    assert response.status_code == 200
    assert response.json() == detail.model_dump(mode="json")


@pytest.mark.asyncio
async def test_unsupported_contract_returns_typed_409(authenticated_app) -> None:
    summary, _ = _projection()
    error = AgentEvidenceError(
        "unsupported_contract",
        "unsupported",
        [diagnostic("unsupported_contract", "contract", "unsupported")],
    )
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.service.get_agent_execution",
        new=AsyncMock(side_effect=error),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/agent-executions/{summary.trace_id}/{summary.agent_span_id}"
            )
    assert response.status_code == 409
    assert response.json()["code"] == "unsupported_contract"
    assert response.json()["diagnostics"][0]["code"] == "unsupported_contract"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attribute", "value", "expected_diagnostic"),
    [
        (
            "junjo.agent.model_request.count",
            2**53,
            "invalid_contract_integer",
        ),
        ("junjo.agent.name", "\ud800", "nonportable_scalar_text"),
        (
            "junjo.executable_structural_id",
            "agent_sha256:" + "g" * 64,
            "invalid_agent_structural_id",
        ),
    ],
    ids=["unsafe_integer", "invalid_unicode_surrogate", "invalid_structural_id"],
)
async def test_raw_nonportable_owner_scalar_returns_typed_409(
    authenticated_app,
    attribute: str,
    value: object,
    expected_diagnostic: str,
) -> None:
    fixture = copy.deepcopy(json.loads(AGENT_FIXTURE_PATH.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    owner["attributes_json"][attribute] = value
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.repository.get_agent_trace",
        new=AsyncMock(return_value=fixture["spans"]),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/agent-executions/{owner['trace_id']}/{owner['span_id']}"
            )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "unidentifiable_agent"
    assert expected_diagnostic in {item["code"] for item in body["diagnostics"]}


@pytest.mark.parametrize(
    ("attribute", "expected_diagnostic"),
    [
        ("junjo.span_type", "invalid_agent_owner_type"),
        ("junjo.agent.outcome", "invalid_terminal_fact"),
    ],
)
@pytest.mark.parametrize("malformed", [{}, []], ids=["object", "array"])
@pytest.mark.asyncio
async def test_unhashable_agent_owner_scalar_returns_typed_409(
    authenticated_app,
    attribute: str,
    expected_diagnostic: str,
    malformed: object,
) -> None:
    fixture = copy.deepcopy(json.loads(AGENT_FIXTURE_PATH.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    owner["attributes_json"][attribute] = malformed
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.repository.get_agent_trace",
        new=AsyncMock(return_value=fixture["spans"]),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/agent-executions/{owner['trace_id']}/{owner['span_id']}"
            )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "unidentifiable_agent"
    assert expected_diagnostic in {item["code"] for item in body["diagnostics"]}


@pytest.mark.asyncio
async def test_missing_operation_events_return_partial_detail_not_server_error(
    authenticated_app,
) -> None:
    fixture = copy.deepcopy(json.loads(AGENT_FIXTURE_PATH.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    model = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
    )
    model["events_json"] = None
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.repository.get_agent_trace",
        new=AsyncMock(return_value=fixture["spans"]),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/agent-executions/{owner['trace_id']}/{owner['span_id']}"
            )

    assert response.status_code == 200
    body = response.json()
    assert body["integrity"]["status"] == "partial"
    assert "missing_operation_event_evidence" in {
        item["code"] for item in body["integrity"]["diagnostics"]
    }


@pytest.mark.asyncio
async def test_nonportable_child_span_id_returns_portable_partial_detail(
    authenticated_app,
) -> None:
    fixture = copy.deepcopy(json.loads(AGENT_FIXTURE_PATH.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    model = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
    )
    model["span_id"] = "\ud800"
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.repository.get_agent_trace",
        new=AsyncMock(return_value=fixture["spans"]),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/agent-executions/{owner['trace_id']}/{owner['span_id']}"
            )

    assert response.status_code == 200
    body = response.json()
    assert body["integrity"]["status"] == "partial"
    assert "invalid_model_operation" in {item["code"] for item in body["integrity"]["diagnostics"]}
    assert all(
        "\ud800" not in item["path"] and "\ud800" not in item["message"]
        for item in body["integrity"]["diagnostics"]
    )


@pytest.mark.asyncio
async def test_excessively_nested_payload_returns_typed_partial_detail(
    authenticated_app,
) -> None:
    fixture = copy.deepcopy(json.loads(AGENT_FIXTURE_PATH.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    nested: object = "leaf"
    for _ in range(130):
        nested = [nested]
    owner["attributes_json"]["junjo.agent.input"] = json.dumps(nested)
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.repository.get_agent_trace",
        new=AsyncMock(return_value=fixture["spans"]),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/agent-executions/{owner['trace_id']}/{owner['span_id']}"
            )

    assert response.status_code == 200
    body = response.json()
    assert body["integrity"]["status"] == "partial"
    assert "payload_nesting_too_deep" in {item["code"] for item in body["integrity"]["diagnostics"]}


@pytest.mark.asyncio
async def test_partial_store_with_observed_tool_returns_representable_detail(
    authenticated_app,
) -> None:
    fixture = copy.deepcopy(json.loads(MULTI_TOOL_FIXTURE_PATH.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    first_store_event = next(
        event
        for span in fixture["spans"]
        for event in span["events_json"]
        if event["name"] == "set_state"
    )
    first_store_event["attributes"].pop("junjo.store.action")
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.repository.get_agent_trace",
        new=AsyncMock(return_value=fixture["spans"]),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/agent-executions/{owner['trace_id']}/{owner['span_id']}"
            )

    assert response.status_code == 200
    body = response.json()
    requested_calls = [
        call
        for operation in body["operations"]
        if operation["operation_type"] == "model_request"
        for call in operation["requested_tool_calls"]
    ]
    assert body["integrity"]["status"] == "partial"
    assert any(
        call["observed_tool_operation"]
        and call["admission"] == "unknown"
        and call["reason"] == "store_evidence_unavailable"
        for call in requested_calls
    )


@pytest.mark.asyncio
async def test_non_completed_agent_with_unexpected_output_returns_partial_detail(
    authenticated_app,
) -> None:
    fixture = copy.deepcopy(json.loads(LIMIT_FIXTURE_PATH.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    attributes = owner["attributes_json"]
    attributes["junjo.agent.output"] = "null"
    attributes["junjo.agent.output.mode"] = "full"
    attributes["junjo.agent.output.policy"] = "junjo.full.v1"
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.repository.get_agent_trace",
        new=AsyncMock(return_value=fixture["spans"]),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/agent-executions/{owner['trace_id']}/{owner['span_id']}"
            )

    assert response.status_code == 200
    body = response.json()
    assert body["output"] is None
    assert body["integrity"]["status"] == "partial"
    assert "unexpected_output_evidence" in {
        item["code"] for item in body["integrity"]["diagnostics"]
    }


@pytest.mark.parametrize("malformed", [{}, []], ids=["object", "array"])
@pytest.mark.asyncio
async def test_nonscalar_store_action_returns_partial_detail_without_500(
    authenticated_app,
    malformed: object,
) -> None:
    fixture = copy.deepcopy(json.loads(AGENT_FIXTURE_PATH.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    first_store_event = next(
        event
        for span in fixture["spans"]
        for event in span["events_json"]
        if event["name"] == "set_state"
    )
    first_store_event["attributes"]["junjo.store.action"] = malformed
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.agent_diagnostics.repository.get_agent_trace",
        new=AsyncMock(return_value=fixture["spans"]),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/agent-executions/{owner['trace_id']}/{owner['span_id']}"
            )

    assert response.status_code == 200
    body = response.json()
    assert body["integrity"]["status"] == "partial"
    assert "store_causal_owner_mismatch" in {
        item["code"] for item in body["integrity"]["diagnostics"]
    }
