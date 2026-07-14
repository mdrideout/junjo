"""Contract and HTTP tests for cohesive trace evidence."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.features.auth.dependencies import get_authenticated_user
from app.features.trace_evidence.assembler import assemble_trace_evidence
from app.main import app

FIXTURE_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "telemetry"
    / "fixtures"
    / "agent"
    / "producer"
    / "tool_invokes_nested_workflow.json"
)
RAW_SPAN_FIELDS = {
    "trace_id",
    "span_id",
    "parent_span_id",
    "service_name",
    "name",
    "kind",
    "start_time",
    "end_time",
    "status_code",
    "status_message",
    "attributes_json",
    "events_json",
    "links_json",
    "trace_flags",
    "trace_state",
    "dropped_attributes_count",
    "dropped_events_count",
    "dropped_links_count",
    "resource_attributes_json",
    "resource_dropped_attributes_count",
}


def _fixture() -> tuple[str, list[dict]]:
    spans = json.loads(FIXTURE_PATH.read_text())["spans"]
    return spans[0]["trace_id"], spans


@pytest.fixture
def authenticated_app(mock_authenticated_user):
    app.dependency_overrides[get_authenticated_user] = lambda: mock_authenticated_user
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_authenticated_user, None)


def test_trace_evidence_is_lossless_and_indexes_independent_owners() -> None:
    trace_id, spans = _fixture()

    evidence = assemble_trace_evidence(trace_id, spans)

    assert len(evidence.spans) == len(spans)
    assert [span.model_dump() for span in evidence.spans] == spans
    assert all(set(span.model_dump()) == RAW_SPAN_FIELDS for span in evidence.spans)

    agent = next(
        executable
        for executable in evidence.executables_by_span_id.values()
        if executable.executable_type == "agent"
    )
    assert agent.owner_span_id == agent.summary.agent_span_id
    assert agent.runtime_id in evidence.operations_by_owner_runtime_id
    assert set(evidence.operations_by_owner_runtime_id[agent.runtime_id]) == {
        span["span_id"]
        for span in spans
        if span["attributes_json"].get("junjo.agent.runtime_id") == agent.runtime_id
        and span["attributes_json"].get("junjo.agent.operation_type") in {
            "model_request",
            "tool",
        }
    }
    assert agent.store_id in evidence.stores_by_id
    assert evidence.stores_by_id[agent.store_id].owner_span_id == agent.owner_span_id
    assert evidence.relationships_by_owner_span_id[agent.owner_span_id].nested


def test_trace_evidence_preserves_raw_span_when_annotation_is_unsupported() -> None:
    trace_id, source_spans = _fixture()
    spans = copy.deepcopy(source_spans)
    owner = next(
        span for span in spans if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    owner["attributes_json"]["junjo.telemetry.contract_version"] = 999

    evidence = assemble_trace_evidence(trace_id, spans)

    assert len(evidence.spans) == len(spans)
    assert owner["span_id"] not in evidence.executables_by_span_id
    assert "unsupported_contract" in {
        diagnostic.issue.code
        for diagnostic in evidence.diagnostics
        if diagnostic.owner_span_id == owner["span_id"]
    }


@pytest.mark.asyncio
async def test_trace_evidence_route_requires_authentication() -> None:
    trace_id, _ = _fixture()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/trace-evidence/{trace_id}")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_trace_evidence_route_returns_one_cohesive_document(authenticated_app) -> None:
    trace_id, spans = _fixture()
    evidence = assemble_trace_evidence(trace_id, spans)
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.trace_evidence.service.get_trace_evidence",
        new=AsyncMock(return_value=evidence),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/trace-evidence/{trace_id}")

    assert response.status_code == 200
    assert response.json() == evidence.model_dump(mode="json")


@pytest.mark.asyncio
async def test_trace_evidence_route_returns_not_found(authenticated_app) -> None:
    trace_id, _ = _fixture()
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.trace_evidence.service.get_trace_evidence",
        new=AsyncMock(return_value=None),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/trace-evidence/{trace_id}")

    assert response.status_code == 404


def test_trace_evidence_openapi_keeps_transport_validation_explicit() -> None:
    responses = app.openapi()["paths"]["/api/v1/trace-evidence/{trace_id}"]["get"][
        "responses"
    ]
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HTTPValidationError"
    }
