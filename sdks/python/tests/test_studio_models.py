"""Unit contracts for strict public Studio DTOs and comparison projection."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from junjo.studio import (
    AttemptResultWrite,
    AttemptStatus,
    CaseCreate,
    CaseOrigin,
    ExecutableType,
    RunComparisonError,
    RunDetail,
    RunScope,
    SemanticExecutionReference,
    TargetKind,
    project_run_comparison,
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
        "source_execution": None,
        "source_revision": None,
        "created_at": NOW,
    }


def _run(run_id: str, run_label: str) -> dict[str, Any]:
    return {
        "id": run_id,
        "dataset_id": "dataset-1",
        "request_key": run_id,
        "run_label": run_label,
        "source_revision": ("a" if run_id == "baseline" else "b") * 40,
        "status": "completed",
        "created_by_user_id": "user-1",
        "created_at": NOW,
        "completed_at": NOW,
    }


def _attempt(
    attempt_id: str,
    run_id: str,
    *,
    duration_ms: int | None,
) -> dict[str, Any]:
    return {
        "id": attempt_id,
        "run_id": run_id,
        "case_id": "case-1",
        "status": "passed",
        "reason": "Plausible.",
        "duration_ms": duration_ms,
        "subject_execution": None,
        "execution_bound_at": None,
        "recorded_at": NOW,
    }


def _run_detail(
    run_id: str,
    run_label: str,
    *,
    duration_ms: int | None,
) -> RunDetail:
    return RunDetail.model_validate_json(
        json.dumps(
            {
                "run": _run(run_id, run_label),
                "dataset": _dataset(),
                "cases": [
                    {
                        "case": _case(),
                        "attempt": _attempt(
                            f"attempt-{run_id}",
                            run_id,
                            duration_ms=duration_ms,
                        ),
                    }
                ],
            }
        )
    )


def test_models_are_strict_frozen_and_closed() -> None:
    with pytest.raises(ValidationError, match="extra"):
        SemanticExecutionReference.model_validate(
            {
                "service_namespace": "junjo.examples",
                "service_name": "ai-chat",
                "executable_type": "agent",
                "runtime_id": "agent-1",
                "unexpected": True,
            }
        )

    with pytest.raises(ValidationError):
        CaseCreate.model_validate(
            {
                "case_key": "case",
                "evaluation_name": "Exact match",
                "origin": "authored",
                "target_kind": "node",
                "target_key": "target",
                "target_name": "Target Node",
                "input_version": "1",
                "input_json": {},
                "evaluator_key": "exact",
                "evaluator_version": 1,
            }
        )

    request = CaseCreate(
        case_key="case",
        evaluation_name="Exact match",
        origin=CaseOrigin.AUTHORED,
        target_kind=TargetKind.AGENT,
        target_key="direct-agent",
        target_name="Direct Agent",
        input_version=1,
        input_json={},
        evaluator_key="exact",
        evaluator_version=1,
    )
    with pytest.raises(ValidationError, match="frozen"):
        request.case_key = "changed"  # type: ignore[misc]


def test_case_provenance_and_payload_bounds_match_studio() -> None:
    execution = SemanticExecutionReference(
        service_namespace="junjo.examples",
        service_name="ai-chat",
        executable_type=ExecutableType.WORKFLOW,
        runtime_id="workflow-1",
    )
    with pytest.raises(ValidationError, match="source provenance"):
        CaseCreate(
            case_key="authored",
            evaluation_name="Exact match",
            origin=CaseOrigin.AUTHORED,
            target_kind=TargetKind.NODE,
            target_key="node",
            target_name="Node",
            input_version=1,
            input_json={},
            evaluator_key="exact",
            evaluator_version=1,
            source_execution=execution,
            source_revision="a" * 40,
        )
    with pytest.raises(ValidationError, match="require both"):
        CaseCreate(
            case_key="generated",
            evaluation_name="Exact match",
            origin=CaseOrigin.GENERATED,
            target_kind=TargetKind.WORKFLOW,
            target_key="workflow",
            target_name="Workflow",
            input_version=1,
            input_json={},
            evaluator_key="exact",
            evaluator_version=1,
            source_execution=execution,
        )
    with pytest.raises(ValidationError, match="16384"):
        CaseCreate(
            case_key="large",
            evaluation_name="Exact match",
            origin=CaseOrigin.AUTHORED,
            target_kind=TargetKind.NODE,
            target_key="node",
            target_name="Node",
            input_version=1,
            input_json={"value": "x" * 16_384},
            evaluator_key="exact",
            evaluator_version=1,
        )


@pytest.mark.parametrize("status", tuple(AttemptStatus)[1:])
def test_attempt_result_contract_is_binary(status: AttemptStatus) -> None:
    AttemptResultWrite(status=status, reason="bounded reason")
    with pytest.raises(ValidationError, match="extra"):
        AttemptResultWrite.model_validate({"status": status, "reason": "bounded reason", "score": 1.0})


def test_comparison_aligns_exact_case_identity_and_derives_deltas() -> None:
    baseline = _run_detail(
        "baseline",
        "baseline",
        duration_ms=120,
    )
    candidate = _run_detail(
        "candidate",
        "candidate",
        duration_ms=100,
    )

    comparison = project_run_comparison(baseline, candidate)

    assert comparison.dataset.id == "dataset-1"
    assert comparison.scope.dataset_id == "dataset-1"
    assert comparison.rows[0].case.case_key == "brooklyn"
    assert comparison.rows[0].duration_delta_ms == -20
    assert comparison.rows[0].transition == "unchanged"
    assert comparison.baseline_summary.pass_rate == 1.0
    assert comparison.candidate_summary.pass_rate == 1.0
    assert comparison.transition_counts.unchanged == 1

    scoped = project_run_comparison(
        baseline,
        candidate,
        scope=RunScope(
            target_kind=TargetKind.AGENT,
            evaluation_name="Response place realism",
        ),
    )
    assert scoped.rows == ()
    assert scoped.baseline_summary.total == 0
    assert scoped.scope.target_kind is TargetKind.AGENT


def test_comparison_rejects_same_run_or_different_membership() -> None:
    baseline = _run_detail(
        "baseline",
        "baseline",
        duration_ms=120,
    )
    with pytest.raises(RunComparisonError, match="must differ"):
        project_run_comparison(baseline, baseline)

    candidate = _run_detail(
        "candidate",
        "candidate",
        duration_ms=100,
    )
    mismatched = candidate.model_copy(update={"dataset": candidate.dataset.model_copy(update={"id": "other"})})
    with pytest.raises(RunComparisonError, match="same locked dataset"):
        project_run_comparison(baseline, mismatched)
