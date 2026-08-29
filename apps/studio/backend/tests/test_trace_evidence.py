"""Contract and HTTP tests for cohesive trace evidence."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.features.evaluation.schemas import (
    OpenTelemetrySpanReference,
    SemanticExecutionReference,
)
from app.features.evaluation_tokens.dependencies import get_evidence_read_access
from app.features.execution_resolution.contract import ExecutionResolutionConflictError
from app.features.trace_evidence.assembler import (
    assemble_attempt_evidence_manifest,
    assemble_trace_evidence,
    select_attempt_span_evidence,
)
from app.features.trace_evidence.schemas import AttemptEvidenceSubject
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
FAILURE_FIXTURE_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "telemetry"
    / "fixtures"
    / "agent"
    / "producer"
    / "multi_tool_first_failure.json"
)
UNAVAILABLE_STORE_FIXTURE_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "telemetry"
    / "fixtures"
    / "agent"
    / "producer"
    / "boundary_input_history_rejection.json"
)
HOOK_FAILURE_FIXTURE_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "telemetry"
    / "fixtures"
    / "workflow"
    / "hook_failure_on_surrounding_span.json"
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


def _failure_fixture() -> tuple[str, list[dict]]:
    spans = json.loads(FAILURE_FIXTURE_PATH.read_text())["spans"]
    return spans[0]["trace_id"], spans


def _subject(trace_id: str, owner: dict, *, attempt_id: str = "attempt-id"):
    reference = OpenTelemetrySpanReference(
        service_namespace=owner["resource_attributes_json"].get("service.namespace", ""),
        service_name=owner["resource_attributes_json"]["service.name"],
        trace_id=trace_id,
        span_id=owner["span_id"],
    )
    return AttemptEvidenceSubject(
        attempt_id=attempt_id,
        reference=reference,
        trace_id=trace_id,
        span_id=owner["span_id"],
        detail_path="/detail",
        failure_path="/failure",
        trace_path="/trace",
    )


@pytest.fixture
def authenticated_app(mock_authenticated_user):
    app.dependency_overrides[get_evidence_read_access] = lambda: mock_authenticated_user
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_evidence_read_access, None)


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
        and span["attributes_json"].get("junjo.agent.operation_type")
        in {
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


def test_attempt_manifest_is_payload_light_and_projects_every_failure() -> None:
    trace_id, spans = _failure_fixture()
    evidence = assemble_trace_evidence(trace_id, spans)
    subject = _subject(trace_id, spans[0])

    manifest = assemble_attempt_evidence_manifest(subject=subject, evidence=evidence)

    assert manifest.subject == subject
    assert manifest.trace.span_count == len(spans)
    assert manifest.trace.root_span_ids == [spans[0]["span_id"]]
    assert [entry.span_id for entry in manifest.spans] == [span["span_id"] for span in spans]
    assert all("attributes_json" not in entry.model_dump() for entry in manifest.spans)
    assert [failure.span_id for failure in manifest.failures] == [
        spans[0]["span_id"],
        spans[2]["span_id"],
    ]
    assert all(failure.stacktrace_available for failure in manifest.failures)
    assert all(failure.start_time and failure.end_time for failure in manifest.failures)
    assert {failure.owner_span_id for failure in manifest.failures} == {spans[0]["span_id"]}
    assert {failure.owner_runtime_id for failure in manifest.failures} == {
        manifest.executables[0].runtime_id
    }
    assert manifest.failures[1].exception_type == "junjo.agent.errors.AgentToolError"
    assert manifest.failures[1].exception_message == "Tool 'lookup' service failed."
    assert len(manifest.operations) == 2
    assert all("request" not in operation.model_dump() for operation in manifest.operations)
    assert manifest.stores[0].transition_count == 5
    assert "transitions" not in manifest.stores[0].model_dump()


def test_attempt_manifest_summarizes_openinference_and_gen_ai_operations() -> None:
    trace_id, source_spans = _fixture()
    template = copy.deepcopy(source_spans[0])
    template.update(
        {
            "span_id": "1" * 16,
            "parent_span_id": None,
            "name": "evaluation attempt",
            "attributes_json": {},
            "events_json": [],
            "links_json": [],
            "status_code": "1",
            "status_message": "",
        }
    )
    openinference_model = copy.deepcopy(template)
    openinference_model.update(
        {
            "span_id": "2" * 16,
            "parent_span_id": template["span_id"],
            "name": "AsyncGenerateContent",
            "attributes_json": {
                "openinference.span.kind": "LLM",
                "llm.model_name": "gemini-3.7-flash",
            },
        }
    )
    gen_ai_tool = copy.deepcopy(template)
    gen_ai_tool.update(
        {
            "span_id": "3" * 16,
            "parent_span_id": template["span_id"],
            "name": "execute_tool lookup",
            "attributes_json": {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": "lookup",
            },
        }
    )
    spans = [template, openinference_model, gen_ai_tool]
    evidence = assemble_trace_evidence(trace_id, spans)

    manifest = assemble_attempt_evidence_manifest(
        subject=_subject(trace_id, template),
        evidence=evidence,
    )

    assert [span.semantic_kind for span in manifest.spans] == ["span", "model", "tool"]
    assert [operation.span_id for operation in manifest.operations] == [
        openinference_model["span_id"],
        gen_ai_tool["span_id"],
    ]
    assert [operation.name for operation in manifest.operations] == [
        "gemini-3.7-flash",
        "lookup",
    ]
    assert all(operation.owner_span_id is None for operation in manifest.operations)
    assert all(operation.owner_runtime_id is None for operation in manifest.operations)
    assert all(operation.duration_ns is None for operation in manifest.operations)


def test_attempt_manifest_preserves_hook_and_status_failure_messages() -> None:
    spans = copy.deepcopy(json.loads(HOOK_FAILURE_FIXTURE_PATH.read_text())["spans"])
    trace_id = spans[0]["trace_id"]
    hook_span = next(
        span
        for span in spans
        if any(event.get("name") == "junjo.hook_error" for event in span["events_json"])
    )
    hook_attributes = hook_span["events_json"][0]["attributes"]
    hook_attributes.pop("exception.type")
    hook_attributes.pop("exception.message")
    status_failure = copy.deepcopy(hook_span)
    status_failure.update(
        {
            "span_id": "7" * 16,
            "name": "external model request",
            "status_code": "2",
            "status_message": "provider request failed",
            "attributes_json": {"openinference.span.kind": "LLM"},
            "events_json": [],
        }
    )
    spans.append(status_failure)
    evidence = assemble_trace_evidence(trace_id, spans)

    manifest = assemble_attempt_evidence_manifest(
        subject=_subject(trace_id, spans[0]),
        evidence=evidence,
    )
    failures = {failure.span_id: failure for failure in manifest.failures}

    assert failures[hook_span["span_id"]].exception_type == "RuntimeError"
    assert failures[hook_span["span_id"]].exception_message == "hook exploded"
    assert failures[hook_span["span_id"]].stacktrace_available is True
    assert failures[status_failure["span_id"]].exception_message == "provider request failed"


def test_selected_spans_preserve_order_and_direct_semantic_evidence() -> None:
    trace_id, spans = _failure_fixture()
    evidence = assemble_trace_evidence(trace_id, spans)
    subject = _subject(trace_id, spans[0])
    missing_span_id = "f" * 16

    selected = select_attempt_span_evidence(
        subject=subject,
        evidence=evidence,
        span_ids=[spans[2]["span_id"], spans[0]["span_id"], missing_span_id],
    )

    assert [item.span.span_id for item in selected.items] == [
        spans[2]["span_id"],
        spans[0]["span_id"],
    ]
    assert selected.missing_span_ids == [missing_span_id]
    assert selected.items[0].operation is not None
    assert selected.items[0].executable is None
    assert selected.items[0].stores == []
    assert selected.items[1].executable is not None
    assert selected.items[1].operation is None
    assert selected.items[1].stores[0].owner_span_id == spans[0]["span_id"]


def test_attempt_manifest_reports_unavailable_store_integrity() -> None:
    spans = json.loads(UNAVAILABLE_STORE_FIXTURE_PATH.read_text())["spans"]
    trace_id = spans[0]["trace_id"]
    evidence = assemble_trace_evidence(trace_id, spans)

    manifest = assemble_attempt_evidence_manifest(
        subject=_subject(trace_id, spans[0]),
        evidence=evidence,
    )

    unavailable = [store for store in manifest.stores if not store.available]
    assert unavailable
    assert all(store.store_id is None for store in unavailable)
    assert all(store.transition_count == 0 for store in unavailable)
    assert all(not store.reconstructable for store in unavailable)
    assert all(store.reconstruction_status == "not_applicable" for store in unavailable)


def test_attempt_manifest_does_not_misattribute_duplicate_store_identity() -> None:
    trace_id, source_spans = _fixture()
    spans = copy.deepcopy(source_spans)
    agent_span = next(
        span for span in spans if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    workflow_span = next(
        span for span in spans if span["attributes_json"].get("junjo.span_type") == "workflow"
    )
    duplicate_store_id = agent_span["attributes_json"]["junjo.agent.store.id"]
    workflow_span["attributes_json"]["junjo.workflow.store.id"] = duplicate_store_id
    evidence = assemble_trace_evidence(trace_id, spans)

    manifest = assemble_attempt_evidence_manifest(
        subject=_subject(trace_id, agent_span),
        evidence=evidence,
    )

    assert any(
        diagnostic.issue.code == "duplicate_store_identity" for diagnostic in manifest.diagnostics
    )
    assert {store.owner_span_id for store in manifest.stores} == {agent_span["span_id"]}
    assert workflow_span["span_id"] not in {store.owner_span_id for store in manifest.stores}


@pytest.mark.asyncio
async def test_trace_evidence_route_requires_authentication() -> None:
    trace_id, _ = _fixture()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/trace-evidence/{trace_id}")

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", "/api/v1/trace-evidence/attempts/attempt-id/manifest", None),
        (
            "POST",
            "/api/v1/trace-evidence/attempts/attempt-id/spans",
            {"span_ids": ["a" * 16]},
        ),
    ],
)
async def test_attempt_evidence_routes_require_authentication(
    method: str,
    path: str,
    json_body: dict | None,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(method, path, json=json_body)

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


@pytest.mark.asyncio
async def test_attempt_evidence_routes_return_manifest_and_selected_spans(
    authenticated_app,
) -> None:
    trace_id, spans = _failure_fixture()
    evidence = assemble_trace_evidence(trace_id, spans)
    subject = _subject(trace_id, spans[0])
    manifest = assemble_attempt_evidence_manifest(subject=subject, evidence=evidence)
    selected = select_attempt_span_evidence(
        subject=subject,
        evidence=evidence,
        span_ids=[spans[0]["span_id"]],
    )
    transport = ASGITransport(app=authenticated_app)
    with (
        patch(
            "app.features.trace_evidence.service.get_attempt_evidence_manifest",
            new=AsyncMock(return_value=manifest),
        ),
        patch(
            "app.features.trace_evidence.service.get_attempt_span_evidence",
            new=AsyncMock(return_value=selected),
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            manifest_response = await client.get(
                "/api/v1/trace-evidence/attempts/attempt-id/manifest"
            )
            spans_response = await client.post(
                "/api/v1/trace-evidence/attempts/attempt-id/spans",
                json={"span_ids": [spans[0]["span_id"]]},
            )

    assert manifest_response.status_code == 200
    assert manifest_response.json() == manifest.model_dump(mode="json")
    assert spans_response.status_code == 200
    assert spans_response.json() == selected.model_dump(mode="json")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "json_body", "service_method"),
    [
        (
            "GET",
            "/api/v1/trace-evidence/attempts/attempt-id/manifest",
            None,
            "get_attempt_evidence_manifest",
        ),
        (
            "POST",
            "/api/v1/trace-evidence/attempts/attempt-id/spans",
            {"span_ids": ["a" * 16]},
            "get_attempt_span_evidence",
        ),
    ],
)
async def test_attempt_evidence_routes_return_typed_resolution_conflicts(
    authenticated_app,
    method: str,
    path: str,
    json_body: dict | None,
    service_method: str,
) -> None:
    transport = ASGITransport(app=authenticated_app)
    with patch(
        f"app.features.trace_evidence.service.{service_method}",
        new=AsyncMock(side_effect=ExecutionResolutionConflictError(match_count=2)),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.request(method, path, json=json_body)

    assert response.status_code == 409
    assert response.json() == {
        "code": "ambiguous_execution_identity",
        "message": "Execution identity resolved to multiple owner spans.",
        "match_count": 2,
    }


@pytest.mark.asyncio
async def test_selected_span_route_rejects_empty_duplicate_and_invalid_ids(
    authenticated_app,
) -> None:
    transport = ASGITransport(app=authenticated_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [
            await client.post(
                "/api/v1/trace-evidence/attempts/attempt-id/spans",
                json=body,
            )
            for body in (
                {"span_ids": []},
                {"span_ids": ["a" * 16, "a" * 16]},
                {"span_ids": ["A" * 16]},
            )
        ]

    assert [response.status_code for response in responses] == [422, 422, 422]


@pytest.mark.asyncio
async def test_attempt_manifest_resolves_otel_subject_and_fails_closed_on_service_mismatch() -> (
    None
):
    trace_id, spans = _failure_fixture()
    evidence = assemble_trace_evidence(trace_id, spans)
    reference = _subject(trace_id, spans[0]).reference
    attempt = SimpleNamespace(attempt=SimpleNamespace(subject_evidence=reference))
    with (
        patch(
            "app.features.trace_evidence.service.evaluation_service.get_attempt",
            new=AsyncMock(return_value=attempt),
        ),
        patch(
            "app.features.trace_evidence.service.get_trace_evidence",
            new=AsyncMock(return_value=evidence),
        ),
    ):
        from app.features.trace_evidence.service import get_attempt_evidence_manifest

        manifest = await get_attempt_evidence_manifest("attempt-id")
        attempt.attempt.subject_evidence = reference.model_copy(
            update={"service_name": "wrong-service"}
        )
        mismatched = await get_attempt_evidence_manifest("attempt-id")

    assert manifest is not None
    assert manifest.subject.span_id == spans[0]["span_id"]
    assert mismatched is None


@pytest.mark.asyncio
async def test_attempt_manifest_resolves_semantic_subject() -> None:
    trace_id, spans = _failure_fixture()
    evidence = assemble_trace_evidence(trace_id, spans)
    owner = evidence.executables_by_span_id[spans[0]["span_id"]]
    reference = SemanticExecutionReference(
        service_namespace=spans[0]["resource_attributes_json"].get("service.namespace", ""),
        service_name=spans[0]["resource_attributes_json"]["service.name"],
        executable_type="agent",
        runtime_id=owner.runtime_id,
    )
    attempt = SimpleNamespace(attempt=SimpleNamespace(subject_evidence=reference))
    resolution = SimpleNamespace(
        trace_id=trace_id,
        span_id=spans[0]["span_id"],
        detail_path="/agents/detail",
        failure_path="/agents/failure",
        trace_path="/traces/detail",
    )
    with (
        patch(
            "app.features.trace_evidence.service.evaluation_service.get_attempt",
            new=AsyncMock(return_value=attempt),
        ),
        patch(
            "app.features.trace_evidence.service.resolution_service.resolve_execution",
            new=AsyncMock(return_value=resolution),
        ),
        patch(
            "app.features.trace_evidence.service.get_trace_evidence",
            new=AsyncMock(return_value=evidence),
        ),
    ):
        from app.features.trace_evidence.service import get_attempt_evidence_manifest

        manifest = await get_attempt_evidence_manifest("attempt-id")

    assert manifest is not None
    assert manifest.subject.reference == reference
    assert manifest.subject.detail_path == "/agents/detail"


def test_trace_evidence_openapi_keeps_transport_validation_explicit() -> None:
    responses = app.openapi()["paths"]["/api/v1/trace-evidence/{trace_id}"]["get"]["responses"]
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HTTPValidationError"
    }
    schema = app.openapi()
    assert (
        schema["paths"]["/api/v1/trace-evidence/attempts/{attempt_id}/manifest"]["get"][
            "operationId"
        ]
        == "get_attempt_evidence_manifest"
    )
    assert (
        schema["paths"]["/api/v1/trace-evidence/attempts/{attempt_id}/spans"]["post"]["operationId"]
        == "get_attempt_span_evidence"
    )
    for path, method in (
        ("/api/v1/trace-evidence/attempts/{attempt_id}/manifest", "get"),
        ("/api/v1/trace-evidence/attempts/{attempt_id}/spans", "post"),
    ):
        assert schema["paths"][path][method]["security"] == [{"EvaluationControlToken": []}]
