"""Conformance and HTTP tests for authoritative Workflow Store diagnostics."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.features.auth.dependencies import get_authenticated_user
from app.features.workflow_diagnostics.assembler import (
    WorkflowEvidenceError,
    assemble_workflow_store_diagnostic,
)
from app.main import app

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[4] / "contracts" / "telemetry" / "fixtures" / "workflow"
)
GENERATOR_PATH = Path(__file__).parent / "generate_workflow_store_projections.py"
SPEC = importlib.util.spec_from_file_location(
    "workflow_store_projection_generator",
    GENERATOR_PATH,
)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


@pytest.fixture
def authenticated_app(mock_authenticated_user):
    """Run one route test with an explicit authenticated Studio session dependency."""
    app.dependency_overrides[get_authenticated_user] = lambda: mock_authenticated_user
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_authenticated_user, None)


def _workflow_cases() -> list[tuple[str, dict, list[dict]]]:
    cases = []
    for path in sorted(FIXTURE_ROOT.glob("*.json")):
        fixture = json.loads(path.read_text())
        for owner in fixture["spans"]:
            executable_type = owner["attributes_json"].get("junjo.span_type")
            if executable_type in {"workflow", "subflow"}:
                cases.append(
                    (
                        f"{path.stem}:{owner['span_id']}",
                        owner,
                        fixture["spans"],
                    )
                )
    return cases


@pytest.mark.parametrize(
    ("_name", "owner", "spans"),
    _workflow_cases(),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_every_canonical_workflow_store_is_backend_verified(
    _name: str,
    owner: dict,
    spans: list[dict],
) -> None:
    detail = assemble_workflow_store_diagnostic(owner, spans)

    assert detail.state.reconstruction_status == "verified"
    assert detail.state.reconstructable is True
    assert detail.integrity.status == "complete"
    assert detail.integrity.diagnostics == []


def test_generated_workflow_store_projections_are_current() -> None:
    assert GENERATOR.OUTPUT_PATH.read_text() == GENERATOR.render_projections()


def test_generated_workflow_store_projections_cover_every_owner() -> None:
    projections = json.loads(GENERATOR.OUTPUT_PATH.read_text())
    expected_case_names = {name for name, _owner, _spans in _workflow_cases()}

    assert {projection["case_name"] for projection in projections} == expected_case_names


def test_workflow_store_unsafe_scalar_becomes_partial_not_unsafe_json() -> None:
    _name, owner, spans = _workflow_cases()[0]
    owner = copy.deepcopy(owner)
    spans = [
        owner if span["span_id"] == owner["span_id"] else copy.deepcopy(span) for span in spans
    ]
    owner["attributes_json"]["junjo.store.revision.end"] = 2**53

    detail = assemble_workflow_store_diagnostic(owner, spans)

    assert detail.integrity.status == "partial"
    assert detail.state.revision_end is None
    assert "invalid_store_owner_fact" in {issue.code for issue in detail.integrity.diagnostics}


def test_workflow_store_excessive_payload_nesting_is_typed_partial_evidence() -> None:
    _name, original_owner, original_spans = _workflow_cases()[0]
    spans = copy.deepcopy(original_spans)
    owner = next(span for span in spans if span["span_id"] == original_owner["span_id"])
    nested: object = "leaf"
    for _ in range(130):
        nested = [nested]
    owner["attributes_json"]["junjo.workflow.state.start"] = json.dumps(nested)

    detail = assemble_workflow_store_diagnostic(owner, spans)

    assert detail.integrity.status == "partial"
    assert "payload_nesting_too_deep" in {issue.code for issue in detail.integrity.diagnostics}


@pytest.mark.parametrize(
    ("version", "expected_code"),
    [
        (1, "unsupported_contract"),
        (None, "missing_contract_version"),
    ],
    ids=["unsupported", "missing"],
)
def test_workflow_store_excludes_child_evidence_without_active_contract(
    version: int | None,
    expected_code: str,
) -> None:
    _name, original_owner, original_spans = next(
        case for case in _workflow_cases() if case[0].startswith("basic_workflow_success:")
    )
    spans = copy.deepcopy(original_spans)
    owner = next(span for span in spans if span["span_id"] == original_owner["span_id"])
    child = next(span for span in spans if span["name"] == "fetch_input")
    if version is None:
        child["attributes_json"].pop("junjo.telemetry.contract_version")
    else:
        child["attributes_json"]["junjo.telemetry.contract_version"] = version

    detail = assemble_workflow_store_diagnostic(owner, spans)

    assert detail.integrity.status == "partial"
    assert detail.state.reconstruction_status == "failed"
    assert all(transition.span_id != child["span_id"] for transition in detail.state.transitions)
    assert expected_code in {issue.code for issue in detail.integrity.diagnostics}


def test_workflow_store_excludes_transition_on_noncanonical_carrier_span() -> None:
    _name, original_owner, original_spans = next(
        case for case in _workflow_cases() if case[0].startswith("basic_workflow_success:")
    )
    spans = copy.deepcopy(original_spans)
    owner = next(span for span in spans if span["span_id"] == original_owner["span_id"])
    event_span = next(
        span
        for span in spans
        if span is not owner
        and any(event.get("name") == "set_state" for event in span["events_json"])
    )
    event_span["span_id"] = "not-a-span-id"

    detail = assemble_workflow_store_diagnostic(owner, spans)

    assert detail.integrity.status == "partial"
    assert detail.state.reconstruction_status == "failed"
    assert all(transition.span_id != "not-a-span-id" for transition in detail.state.transitions)
    assert "invalid_span_id" in {issue.code for issue in detail.integrity.diagnostics}


@pytest.mark.asyncio
async def test_workflow_store_route_requires_authentication() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/workflow-executions/11111111111111111111111111111111/aaaaaaaaaaaaaaaa/store"
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_workflow_store_route_path_validation_uses_transport_422(
    authenticated_app,
) -> None:
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.workflow_diagnostics.service.get_workflow_store",
        new=AsyncMock(return_value=None),
    ) as query:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/workflow-executions/not-a-trace/not-a-span/store")

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "type": "string_pattern_mismatch",
            "loc": ["path", "trace_id"],
            "msg": "String should match pattern '^[0-9a-f]{32}$'",
            "input": "not-a-trace",
            "ctx": {"pattern": "^[0-9a-f]{32}$"},
        },
        {
            "type": "string_pattern_mismatch",
            "loc": ["path", "workflow_span_id"],
            "msg": "String should match pattern '^[0-9a-f]{16}$'",
            "input": "not-a-span",
            "ctx": {"pattern": "^[0-9a-f]{16}$"},
        },
    ]
    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_store_route_returns_typed_projection(authenticated_app) -> None:
    _name, owner, spans = _workflow_cases()[0]
    detail = assemble_workflow_store_diagnostic(owner, spans)
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.workflow_diagnostics.service.get_workflow_store",
        new=AsyncMock(return_value=detail),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/workflow-executions/{detail.trace_id}/{detail.workflow_span_id}/store"
            )

    assert response.status_code == 200
    assert response.json() == detail.model_dump(mode="json")


@pytest.mark.asyncio
async def test_workflow_store_route_returns_typed_contract_error(authenticated_app) -> None:
    _name, owner, _spans = _workflow_cases()[0]
    error = WorkflowEvidenceError(
        "unsupported_contract",
        "Unsupported telemetry contract.",
    )
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.workflow_diagnostics.service.get_workflow_store",
        new=AsyncMock(side_effect=error),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/workflow-executions/{owner['trace_id']}/{owner['span_id']}/store"
            )

    assert response.status_code == 409
    assert response.json()["code"] == "unsupported_contract"


@pytest.mark.asyncio
async def test_workflow_store_route_preserves_partial_invalid_event_timestamp(
    authenticated_app,
) -> None:
    _name, owner, spans = _workflow_cases()[0]
    spans = copy.deepcopy(spans)
    owner = next(span for span in spans if span["span_id"] == owner["span_id"])
    event_span = next(span for span in spans if span["events_json"])
    event_span["events_json"][0]["timeUnixNano"] = 2**63
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.workflow_diagnostics.repository.get_workflow_trace",
        new=AsyncMock(return_value=spans),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/workflow-executions/{owner['trace_id']}/{owner['span_id']}/store"
            )

    assert response.status_code == 200
    body = response.json()
    assert body["integrity"]["status"] == "partial"
    assert "invalid_event_timestamp" in {item["code"] for item in body["integrity"]["diagnostics"]}


@pytest.mark.asyncio
async def test_workflow_store_route_rejects_nonportable_owner_name_without_500(
    authenticated_app,
) -> None:
    _name, owner, spans = _workflow_cases()[0]
    spans = copy.deepcopy(spans)
    owner = next(span for span in spans if span["span_id"] == owner["span_id"])
    owner["name"] = "\ud800"
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.workflow_diagnostics.repository.get_workflow_trace",
        new=AsyncMock(return_value=spans),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/workflow-executions/{owner['trace_id']}/{owner['span_id']}/store"
            )

    assert response.status_code == 409
    assert response.json()["code"] == "unidentifiable_workflow"


@pytest.mark.parametrize("malformed", [{}, []], ids=["object", "array"])
@pytest.mark.asyncio
async def test_workflow_store_route_rejects_unhashable_owner_type_without_500(
    authenticated_app,
    malformed: object,
) -> None:
    _name, original_owner, original_spans = _workflow_cases()[0]
    spans = copy.deepcopy(original_spans)
    owner = next(span for span in spans if span["span_id"] == original_owner["span_id"])
    owner["attributes_json"]["junjo.span_type"] = malformed
    transport = ASGITransport(app=authenticated_app)
    with patch(
        "app.features.workflow_diagnostics.repository.get_workflow_trace",
        new=AsyncMock(return_value=spans),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/workflow-executions/{owner['trace_id']}/{owner['span_id']}/store"
            )

    assert response.status_code == 409
    assert response.json()["code"] == "unidentifiable_workflow"
