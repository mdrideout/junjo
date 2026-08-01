"""Authenticated HTTP and OpenAPI contract tests for evaluations."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db_sqlite.users.models import UserTable
from app.features.evaluation_tokens.dependencies import (
    get_evaluation_read_access,
    get_evaluation_write_access,
)
from app.main import app

REVISION = "a" * 40
DATASET_BODY = {
    "application_key": "ai_chat",
    "key": "local_place_realism_v1",
    "name": "Local place realism",
    "description": "Require one specific plausible nearby place.",
}
CASE_BODY = {
    "case_key": "specific_place_1",
    "evaluation_name": "Response place realism",
    "origin": "authored",
    "target_kind": "node",
    "target_key": "date_response_node",
    "input_version": 1,
    "input_json": {"prompt": "Name one specific plausible nearby place."},
    "expectation_json": {"rubric": "Names one specific place."},
    "evaluator_key": "response_quality",
    "evaluator_version": 1,
}
EXECUTION_BODY = {
    "execution": {
        "service_namespace": "junjo.examples",
        "service_name": "ai-chat-evaluation",
        "executable_type": "workflow",
        "runtime_id": "workflow-run",
    }
}


@pytest_asyncio.fixture
async def authenticated_app(test_db, mock_authenticated_user) -> AsyncIterator:
    async with test_db() as session:
        session.add(
            UserTable(
                id=mock_authenticated_user.user_id,
                email=mock_authenticated_user.email,
                password_hash="test-only",
            )
        )
        await session.commit()
    app.dependency_overrides[get_evaluation_read_access] = lambda: mock_authenticated_user
    app.dependency_overrides[get_evaluation_write_access] = lambda: mock_authenticated_user
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_evaluation_read_access, None)
        app.dependency_overrides.pop(get_evaluation_write_access, None)


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("POST", "/api/v1/evaluation/datasets", {"json": DATASET_BODY}),
        (
            "GET",
            "/api/v1/evaluation/datasets",
            {"params": {"application_key": "ai_chat"}},
        ),
        ("GET", "/api/v1/evaluation/datasets/dataset-id", {}),
        (
            "POST",
            "/api/v1/evaluation/datasets/dataset-id/cases",
            {"json": CASE_BODY},
        ),
        ("PUT", "/api/v1/evaluation/datasets/dataset-id/lock", {}),
        (
            "POST",
            "/api/v1/evaluation/runs",
            {
                "json": {
                    "dataset_id": "dataset-id",
                    "request_key": "baseline",
                    "run_label": "baseline",
                    "source_revision": REVISION,
                }
            },
        ),
        ("GET", "/api/v1/evaluation/runs", {}),
        ("GET", "/api/v1/evaluation/runs/run-id", {}),
        ("GET", "/api/v1/evaluation/attempts/attempt-id", {}),
        (
            "PUT",
            "/api/v1/evaluation/attempts/attempt-id/execution",
            {"json": EXECUTION_BODY},
        ),
        (
            "PUT",
            "/api/v1/evaluation/attempts/attempt-id/result",
            {"json": {"status": "error", "reason": "Setup failed."}},
        ),
        (
            "GET",
            "/api/v1/evaluation/execution-membership",
            {"params": EXECUTION_BODY["execution"]},
        ),
    ],
)
async def test_every_evaluation_route_requires_session_or_scoped_token(
    method: str,
    path: str,
    kwargs: dict,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(method, path, **kwargs)
    assert response.status_code == 401


async def test_headless_api_loop_and_response_envelopes(authenticated_app) -> None:
    transport = ASGITransport(app=authenticated_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/v1/evaluation/datasets", json=DATASET_BODY)
        assert created.status_code == 200
        dataset = created.json()
        assert dataset["status"] == "draft"

        dataset_detail = await client.get(f"/api/v1/evaluation/datasets/{dataset['id']}")
        assert dataset_detail.json() == {"dataset": dataset, "cases": []}

        draft_run = await client.post(
            "/api/v1/evaluation/runs",
            json={
                "dataset_id": dataset["id"],
                "request_key": "baseline",
                "run_label": "baseline",
                "source_revision": REVISION,
            },
        )
        assert draft_run.status_code == 409
        assert draft_run.json()["code"] == "dataset_not_locked"

        added = await client.post(
            f"/api/v1/evaluation/datasets/{dataset['id']}/cases",
            json=CASE_BODY,
        )
        assert added.status_code == 200
        case = added.json()
        assert case["ordinal"] == 1

        locked = await client.put(f"/api/v1/evaluation/datasets/{dataset['id']}/lock")
        assert locked.status_code == 200
        assert locked.json()["status"] == "locked"

        identical_case = await client.post(
            f"/api/v1/evaluation/datasets/{dataset['id']}/cases",
            json=CASE_BODY,
        )
        assert identical_case.status_code == 200
        assert identical_case.json()["id"] == case["id"]

        started = await client.post(
            "/api/v1/evaluation/runs",
            json={
                "dataset_id": dataset["id"],
                "request_key": "baseline",
                "run_label": "baseline",
                "source_revision": REVISION,
            },
        )
        assert started.status_code == 200
        run_detail = started.json()
        assert set(run_detail) == {"run", "dataset", "cases"}
        assert len(run_detail["cases"]) == 1
        attempt_id = run_detail["cases"][0]["attempt"]["id"]

        attempt_detail = await client.get(f"/api/v1/evaluation/attempts/{attempt_id}")
        assert attempt_detail.status_code == 200
        assert set(attempt_detail.json()) == {"run", "dataset", "case", "attempt"}

        bound = await client.put(
            f"/api/v1/evaluation/attempts/{attempt_id}/execution",
            json=EXECUTION_BODY,
        )
        assert bound.status_code == 200
        assert bound.json()["subject_execution"] == EXECUTION_BODY["execution"]

        recorded = await client.put(
            f"/api/v1/evaluation/attempts/{attempt_id}/result",
            json={
                "status": "passed",
                "reason": "The response names a specific plausible place.",
            },
        )
        assert recorded.status_code == 200
        assert recorded.json()["duration_ms"] is None

        completed = await client.get(f"/api/v1/evaluation/runs/{run_detail['run']['id']}")
        assert completed.status_code == 200
        assert completed.json()["run"]["status"] == "completed"

        listed = await client.get(
            "/api/v1/evaluation/runs",
            params={"dataset_id": dataset["id"]},
        )
        assert listed.status_code == 200
        list_body = listed.json()
        assert set(list_body) == {"scope", "items", "next_cursor"}
        assert list_body["scope"] == {
            "dataset_id": dataset["id"],
            "target_kind": None,
            "target_key": None,
            "input_version": None,
            "evaluation_name": None,
        }
        assert set(list_body["items"][0]) == {
            "run",
            "dataset",
            "outcome_summary",
            "target_facets",
            "evaluation_facets",
        }
        assert set(list_body["items"][0]["dataset"]) == {
            "id",
            "application_key",
            "key",
            "name",
            "status",
        }
        assert list_body["items"][0]["outcome_summary"] == {
            "total": 1,
            "queued": 0,
            "judged": 1,
            "passed": 1,
            "failed": 0,
            "error": 0,
            "pass_rate": 1.0,
            "coverage": 1.0,
        }
        assert list_body["items"][0]["target_facets"] == [
            {
                "target_kind": "node",
                "target_key": "date_response_node",
                "input_version": 1,
                "case_count": 1,
            }
        ]
        assert list_body["items"][0]["evaluation_facets"] == [
            {
                "evaluation_name": "Response place realism",
                "case_count": 1,
            }
        ]

        scoped = await client.get(
            "/api/v1/evaluation/runs",
            params={
                "dataset_id": dataset["id"],
                "target_kind": "node",
                "target_key": "date_response_node",
                "input_version": 1,
                "evaluation_name": "Response place realism",
            },
        )
        assert scoped.status_code == 200
        assert scoped.json()["items"][0]["outcome_summary"]["pass_rate"] == 1.0
        assert scoped.json()["scope"] == {
            "dataset_id": dataset["id"],
            "target_kind": "node",
            "target_key": "date_response_node",
            "input_version": 1,
            "evaluation_name": "Response place realism",
        }

        unmatched = await client.get(
            "/api/v1/evaluation/runs",
            params={"dataset_id": dataset["id"], "target_kind": "agent"},
        )
        assert unmatched.status_code == 200
        assert unmatched.json()["items"] == []

        all_datasets = await client.get("/api/v1/evaluation/datasets")
        assert all_datasets.status_code == 200
        assert [item["id"] for item in all_datasets.json()["items"]] == [dataset["id"]]

        membership = await client.get(
            "/api/v1/evaluation/execution-membership",
            params=EXECUTION_BODY["execution"],
        )
        assert membership.status_code == 200
        assert membership.json() == {
            "items": [
                {
                    "role": "attempt_subject",
                    "dataset_id": dataset["id"],
                    "case_id": case["id"],
                    "run_id": run_detail["run"]["id"],
                    "attempt_id": attempt_id,
                }
            ],
            "next_cursor": None,
        }


async def test_lists_are_bounded_and_reject_malformed_cursors(authenticated_app) -> None:
    transport = ASGITransport(app=authenticated_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        too_large = await client.get(
            "/api/v1/evaluation/runs",
            params={"limit": 101},
        )
        malformed = await client.get(
            "/api/v1/evaluation/runs",
            params={"cursor": "____"},
        )

    assert too_large.status_code == 422
    assert malformed.status_code == 422
    assert malformed.json()["detail"] == "Invalid pagination cursor"


def test_openapi_operation_ids_and_fixed_run_envelopes() -> None:
    schema = app.openapi()
    expected = {
        ("/api/v1/evaluation/datasets", "post"): "create_evaluation_dataset",
        ("/api/v1/evaluation/datasets", "get"): "list_evaluation_datasets",
        (
            "/api/v1/evaluation/datasets/{dataset_id}",
            "get",
        ): "get_evaluation_dataset",
        (
            "/api/v1/evaluation/datasets/{dataset_id}/cases",
            "post",
        ): "add_evaluation_case",
        (
            "/api/v1/evaluation/datasets/{dataset_id}/lock",
            "put",
        ): "lock_evaluation_dataset",
        ("/api/v1/evaluation/runs", "post"): "start_evaluation_run",
        ("/api/v1/evaluation/runs", "get"): "list_evaluation_runs",
        ("/api/v1/evaluation/runs/{run_id}", "get"): "get_evaluation_run",
        (
            "/api/v1/evaluation/attempts/{attempt_id}",
            "get",
        ): "get_evaluation_attempt",
        (
            "/api/v1/evaluation/attempts/{attempt_id}/execution",
            "put",
        ): "bind_evaluation_attempt_execution",
        (
            "/api/v1/evaluation/attempts/{attempt_id}/result",
            "put",
        ): "record_evaluation_attempt_result",
        (
            "/api/v1/evaluation/execution-membership",
            "get",
        ): "find_evaluation_execution_membership",
    }
    for (path, method), operation_id in expected.items():
        assert schema["paths"][path][method]["operationId"] == operation_id
        assert schema["paths"][path][method]["security"] == [{"EvaluationControlToken": []}]

    run_detail = schema["components"]["schemas"]["EvaluationRunDetail"]
    assert set(run_detail["required"]) == {"run", "dataset", "cases"}
    run_list = schema["components"]["schemas"]["EvaluationRunList"]
    assert set(run_list["required"]) == {"scope", "items", "next_cursor"}
    target_kind = schema["components"]["schemas"]["EvaluationCaseCreate"]["properties"][
        "target_kind"
    ]
    assert target_kind["enum"] == ["node", "workflow", "agent"]
