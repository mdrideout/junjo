"""Deterministic transport contracts for the public Studio client."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from junjo.studio import (
    AttemptEvidenceUnavailable,
    AttemptResultWrite,
    AttemptStatus,
    CaseCreate,
    CaseOrigin,
    DatasetCreate,
    ExecutableType,
    ExecutionEvidencePending,
    ExecutionIdentityAmbiguous,
    RunStart,
    SemanticExecutionReference,
    StudioAuthenticationError,
    StudioAuthorizationError,
    StudioClient,
    StudioConflictError,
    StudioContractError,
    StudioResponseTooLargeError,
    StudioTransientError,
    StudioValidationError,
    TargetKind,
)

NOW = "2026-07-27T12:00:00Z"


def _dataset() -> dict[str, Any]:
    return {
        "id": "dataset-1",
        "application_key": "ai_chat",
        "key": "local-places",
        "name": "Local places",
        "status": "locked",
        "description": None,
        "created_by_user_id": "user-1",
        "created_at": NOW,
        "locked_at": NOW,
    }


def _case() -> dict[str, Any]:
    return {
        "id": "case-1",
        "dataset_id": "dataset-1",
        "case_key": "brooklyn",
        "evaluation_name": "Response place realism",
        "ordinal": 1,
        "origin": "authored",
        "target_kind": "node",
        "target_key": "turn.date_response",
        "target_name": "CreateDateIdeaResponseNode",
        "input_version": 1,
        "input_json": {"message": "Pick one place."},
        "expectation_json": {"rubric": "Name a plausible Brooklyn place."},
        "evaluator_key": "text.quality",
        "evaluator_version": 1,
        "source_evidence": None,
        "source_revision": None,
        "created_at": NOW,
    }


def _run(
    *,
    run_id: str = "run-1",
    request_key: str = "baseline-1",
    run_label: str = "baseline",
) -> dict[str, Any]:
    return {
        "id": run_id,
        "dataset_id": "dataset-1",
        "request_key": request_key,
        "run_label": run_label,
        "source_revision": "a" * 40,
        "status": "active",
        "created_by_user_id": "user-1",
        "created_at": NOW,
        "completed_at": None,
    }


def _execution() -> dict[str, Any]:
    return {
        "kind": "junjo_execution",
        "service_namespace": "junjo.examples",
        "service_name": "ai-chat-evals",
        "executable_type": "workflow",
        "runtime_id": "workflow-run",
    }


def _attempt(
    *,
    run_id: str = "run-1",
    attempt_id: str = "attempt-1",
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": attempt_id,
        "run_id": run_id,
        "case_id": "case-1",
        "status": "queued",
        "reason": None,
        "duration_ms": None,
        "subject_evidence": execution,
        "evidence_bound_at": NOW if execution is not None else None,
        "recorded_at": None,
    }


def _run_detail(
    *,
    run_id: str = "run-1",
    request_key: str = "baseline-1",
    run_label: str = "baseline",
) -> dict[str, Any]:
    return {
        "run": _run(
            run_id=run_id,
            request_key=request_key,
            run_label=run_label,
        ),
        "dataset": _dataset(),
        "cases": [
            {
                "case": _case(),
                "attempt": _attempt(
                    run_id=run_id,
                    attempt_id=f"attempt-{run_id}",
                ),
            }
        ],
    }


def _reference() -> SemanticExecutionReference:
    return SemanticExecutionReference(
        service_namespace="junjo.examples",
        service_name="ai-chat-evals",
        executable_type=ExecutableType.WORKFLOW,
        runtime_id="workflow-run",
    )


@pytest.mark.asyncio
async def test_token_authentication_redaction_and_all_control_operations() -> None:
    requests: list[httpx.Request] = []
    execution = _execution()

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer control-secret"
        routes: dict[tuple[str, str], Callable[[], dict[str, Any]]] = {
            ("POST", "/api/v1/evaluation/datasets"): _dataset,
            (
                "GET",
                "/api/v1/evaluation/datasets",
            ): lambda: {"items": [_dataset()], "next_cursor": "dataset-cursor"},
            (
                "GET",
                "/api/v1/evaluation/datasets/dataset-1",
            ): lambda: {"dataset": _dataset(), "cases": [_case()]},
            ("POST", "/api/v1/evaluation/datasets/dataset-1/cases"): _case,
            ("PUT", "/api/v1/evaluation/datasets/dataset-1/lock"): _dataset,
            ("POST", "/api/v1/evaluation/runs"): _run_detail,
            (
                "GET",
                "/api/v1/evaluation/runs",
            ): lambda: {
                "scope": {
                    "dataset_id": "dataset-1",
                    "target_kind": "node",
                    "target_key": "turn.date_response",
                    "input_version": 1,
                    "evaluation_name": "Response place realism",
                },
                "items": [
                    {
                        "run": _run(),
                        "dataset": {
                            "id": "dataset-1",
                            "application_key": "ai_chat",
                            "key": "local-places",
                            "name": "Local places",
                            "status": "locked",
                        },
                        "outcome_summary": {
                            "total": 1,
                            "queued": 1,
                            "judged": 0,
                            "passed": 0,
                            "failed": 0,
                            "error": 0,
                            "pass_rate": None,
                            "coverage": 0.0,
                        },
                        "target_facets": [
                            {
                                "target_kind": "node",
                                "target_key": "turn.date_response",
                                "target_name": "CreateDateIdeaResponseNode",
                                "input_version": 1,
                                "case_count": 1,
                            }
                        ],
                        "evaluation_facets": [
                            {
                                "evaluation_name": "Response place realism",
                                "case_count": 1,
                            }
                        ],
                    }
                ],
                "next_cursor": None,
            },
            ("GET", "/api/v1/evaluation/runs/run-1"): _run_detail,
            (
                "GET",
                "/api/v1/evaluation/attempts/attempt-1",
            ): lambda: {
                "run": _run(),
                "dataset": _dataset(),
                "case": _case(),
                "attempt": _attempt(execution=execution),
            },
            (
                "PUT",
                "/api/v1/evaluation/attempts/attempt-1/evidence",
            ): lambda: _attempt(execution=execution),
            (
                "PUT",
                "/api/v1/evaluation/attempts/attempt-1/result",
            ): _attempt,
            (
                "GET",
                "/api/v1/evaluation/evidence-membership",
            ): lambda: {
                "items": [
                    {
                        "role": "attempt_subject",
                        "dataset_id": "dataset-1",
                        "case_id": "case-1",
                        "run_id": "run-1",
                        "attempt_id": "attempt-1",
                    }
                ],
                "next_cursor": None,
            },
        }
        return httpx.Response(200, json=routes[(request.method, request.url.path)]())

    async with StudioClient(
        base_url="https://studio.test",
        token="control-secret",
        retry_backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    ) as client:
        assert "control-secret" not in repr(client)
        await client.create_dataset(
            DatasetCreate(
                application_key="ai_chat",
                key="local-places",
                name="Local places",
            )
        )
        dataset_page = await client.list_datasets(
            application_key="ai_chat",
            limit=17,
        )
        await client.get_dataset("dataset-1")
        await client.add_case(
            "dataset-1",
            CaseCreate(
                case_key="brooklyn",
                evaluation_name="Response place realism",
                origin=CaseOrigin.AUTHORED,
                target_kind=TargetKind.NODE,
                target_key="turn.date_response",
                target_name="CreateDateIdeaResponseNode",
                input_version=1,
                input_json={"message": "Pick one place."},
                expectation_json={"rubric": "Name a place."},
                evaluator_key="text.quality",
                evaluator_version=1,
            ),
        )
        await client.lock_dataset("dataset-1")
        await client.start_run(
            RunStart(
                dataset_id="dataset-1",
                request_key="baseline-1",
                run_label="baseline",
                source_revision="a" * 40,
            )
        )
        run_page = await client.list_runs(
            dataset_id="dataset-1",
            target_kind=TargetKind.NODE,
            target_key="turn.date_response",
            input_version=1,
            evaluation_name="Response place realism",
            limit=19,
        )
        await client.get_run("run-1")
        await client.get_attempt("attempt-1")
        await client.bind_attempt_evidence("attempt-1", _reference())
        await client.record_attempt_result(
            "attempt-1",
            AttemptResultWrite(
                status=AttemptStatus.ERROR,
                reason="interrupted",
            ),
        )
        membership = await client.get_evidence_membership(
            _reference(),
            cursor="membership-cursor",
            limit=23,
        )

    assert dataset_page.next_cursor == "dataset-cursor"
    assert run_page.scope.target_kind is TargetKind.NODE
    assert membership.items[0].attempt_id == "attempt-1"
    mutations = [request for request in requests if request.method in {"POST", "PUT"}]
    assert all("idempotency-key" not in request.headers for request in mutations)
    list_dataset_request = next(
        request for request in requests if request.method == "GET" and request.url.path == "/api/v1/evaluation/datasets"
    )
    assert dict(list_dataset_request.url.params) == {
        "application_key": "ai_chat",
        "limit": "17",
    }
    list_runs_request = next(
        request for request in requests if request.method == "GET" and request.url.path == "/api/v1/evaluation/runs"
    )
    assert dict(list_runs_request.url.params) == {
        "limit": "19",
        "dataset_id": "dataset-1",
        "target_kind": "node",
        "target_key": "turn.date_response",
        "input_version": "1",
        "evaluation_name": "Response place realism",
    }
    membership_request = next(
        request for request in requests if request.url.path == "/api/v1/evaluation/evidence-membership"
    )
    assert dict(membership_request.url.params) == {
        "kind": "junjo_execution",
        "service_namespace": "junjo.examples",
        "service_name": "ai-chat-evals",
        "executable_type": "workflow",
        "runtime_id": "workflow-run",
        "limit": "23",
        "cursor": "membership-cursor",
    }


@pytest.mark.asyncio
async def test_health_uses_bounded_transport_and_strict_contract_parsing() -> None:
    valid = True

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        if valid:
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "version": "0.82.1",
                    "app_name": "Junjo AI Studio",
                },
            )
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "app_name": "Junjo AI Studio",
            },
        )

    async with StudioClient(
        base_url="https://studio.test",
        token="control-secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        health = await client.get_health()
        assert health.version == "0.82.1"
        valid = False
        with pytest.raises(StudioContractError, match="StudioHealth"):
            await client.get_health()


@pytest.mark.asyncio
async def test_mutation_retries_transport_and_transient_status_with_same_payload() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError("offline", request=request)
        if len(requests) == 2:
            return httpx.Response(503, json={"detail": "starting"})
        return httpx.Response(200, json=_dataset())

    async with StudioClient(
        base_url="https://studio.test",
        token="control-secret",
        retry_attempts=3,
        retry_backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.create_dataset(
            DatasetCreate(
                application_key="ai_chat",
                key="local-places",
                name="Local places",
            )
        )

    assert result.id == "dataset-1"
    assert len(requests) == 3
    assert len({request.content for request in requests}) == 1
    assert all("idempotency-key" not in request.headers for request in requests)


@pytest.mark.asyncio
async def test_conflict_validation_authentication_and_transient_failures_are_distinct() -> None:
    status = 409
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if status == 409:
            return httpx.Response(
                409,
                json={
                    "code": "dataset_content_conflict",
                    "message": "immutable content differs",
                },
            )
        if status == 422:
            return httpx.Response(422, json={"detail": []})
        if status == 401:
            return httpx.Response(401, json={"detail": "unauthorized"})
        if status == 403:
            return httpx.Response(403, json={"detail": "insufficient scope"})
        return httpx.Response(503, json={"detail": "unavailable"})

    async with StudioClient(
        base_url="https://studio.test",
        token="control-secret",
        retry_attempts=2,
        retry_backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    ) as client:
        request = DatasetCreate(
            application_key="ai_chat",
            key="local-places",
            name="Local places",
        )
        with pytest.raises(StudioConflictError) as conflict:
            await client.create_dataset(request)
        assert conflict.value.code == "dataset_content_conflict"
        assert conflict.value.detail == "immutable content differs"
        assert calls == 1

        status = 422
        with pytest.raises(StudioValidationError):
            await client.create_dataset(request)
        assert calls == 2

        status = 401
        with pytest.raises(StudioAuthenticationError):
            await client.create_dataset(request)
        assert calls == 3

        status = 403
        with pytest.raises(StudioAuthorizationError):
            await client.create_dataset(request)
        assert calls == 4

        status = 503
        with pytest.raises(StudioTransientError) as unavailable:
            await client.create_dataset(request)
        assert unavailable.value.status_code == 503
        assert calls == 6


@pytest.mark.asyncio
async def test_resolution_distinguishes_pending_ambiguous_and_invalid_contracts() -> None:
    status = 404

    async def handler(request: httpx.Request) -> httpx.Response:
        if status == 404:
            return httpx.Response(404, json={"detail": "Execution not found"})
        if status == 409:
            return httpx.Response(
                409,
                json={
                    "code": "ambiguous_execution_identity",
                    "message": "two matches",
                    "match_count": 2,
                },
            )
        return httpx.Response(200, json={"unexpected": True})

    async with StudioClient(
        base_url="https://studio.test",
        token="control-secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ExecutionEvidencePending):
            await client.resolve_execution(_reference())
        status = 409
        with pytest.raises(ExecutionIdentityAmbiguous) as ambiguous:
            await client.resolve_execution(_reference())
        assert ambiguous.value.conflict.match_count == 2
        status = 200
        with pytest.raises(StudioContractError):
            await client.resolve_execution(_reference())


@pytest.mark.asyncio
async def test_attempt_evidence_is_explicit_and_preserves_pending_states() -> None:
    trace_id = "a" * 32
    execution = _execution()
    mode = "complete"
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/attempts/attempt-1"):
            return httpx.Response(
                200,
                json={
                    "run": _run(),
                    "dataset": _dataset(),
                    "case": _case(),
                    "attempt": _attempt(execution=None if mode == "unbound" else execution),
                },
            )
        if request.url.path == "/api/v1/execution-resolution":
            return httpx.Response(
                200,
                json={
                    **{key: value for key, value in execution.items() if key != "kind"},
                    "trace_id": trace_id,
                    "span_id": "b" * 16,
                    "detail_path": "/workflows/workflow-run",
                    "trace_path": f"/traces/{trace_id}",
                    "failure_path": "/workflows/workflow-run",
                },
            )
        if mode == "pending-trace":
            return httpx.Response(404, json={"detail": "Trace not found"})
        return httpx.Response(
            200,
            json={
                "trace_id": trace_id,
                "spans": [],
                "executables_by_span_id": {},
                "operations_by_owner_runtime_id": {},
                "stores_by_id": {},
                "relationships_by_owner_span_id": {},
                "diagnostics": [],
            },
        )

    async with StudioClient(
        base_url="https://studio.test",
        token="control-secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.get_attempt_evidence("attempt-1")
        assert result.evidence.trace_id == trace_id
        assert paths == [
            "/api/v1/evaluation/attempts/attempt-1",
            "/api/v1/execution-resolution",
            f"/api/v1/trace-evidence/{trace_id}",
        ]

        mode = "unbound"
        with pytest.raises(AttemptEvidenceUnavailable):
            await client.get_attempt_evidence("attempt-1")

        mode = "pending-trace"
        with pytest.raises(ExecutionEvidencePending):
            await client.get_attempt_evidence("attempt-1")


@pytest.mark.asyncio
async def test_response_byte_budget_is_enforced_while_streaming() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"items":[' + b"x" * 200 + b"]}")

    async with StudioClient(
        base_url="https://studio.test",
        token="control-secret",
        max_control_response_bytes=64,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(StudioResponseTooLargeError) as too_large:
            await client.list_datasets(application_key="ai_chat")

    assert too_large.value.max_bytes == 64


def test_client_rejects_unsafe_origins() -> None:
    with pytest.raises(ValueError, match="loopback"):
        StudioClient(base_url="http://studio.example.com", token="secret")
    with pytest.raises(ValueError, match="credentials"):
        StudioClient(base_url="https://user:password@studio.example.com")
    with pytest.raises(ValueError, match="application path"):
        StudioClient(base_url="https://studio.example.com/prefix")
