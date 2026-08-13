"""Closed input-contract tests for Studio evaluation APIs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.features.evaluation.pagination import decode_time_cursor
from app.features.evaluation.schemas import (
    MAX_JSON_BYTES,
    EvaluationAttemptResult,
    EvaluationCaseCreate,
    SemanticExecutionReference,
)

REVISION = "a" * 40
EXECUTION = {
    "service_namespace": "junjo.examples",
    "service_name": "ai-chat-evaluation",
    "executable_type": "workflow",
    "runtime_id": "workflow-run",
}


def _case(**overrides):
    values = {
        "case_key": "specific_place",
        "evaluation_name": "Response place realism",
        "origin": "authored",
        "target_kind": "node",
        "target_key": "date_response_node",
        "target_name": "CreateDateIdeaResponseNode",
        "input_version": 1,
        "input_json": {"prompt": "Name one specific plausible nearby place."},
        "expectation_json": {"rubric": "Names one specific place."},
        "evaluator_key": "response_quality",
        "evaluator_version": 1,
    }
    values.update(overrides)
    return values


def test_case_provenance_is_all_or_none_and_origin_specific() -> None:
    with pytest.raises(ValidationError):
        EvaluationCaseCreate.model_validate(
            _case(source_execution=EXECUTION, source_revision=REVISION)
        )

    with pytest.raises(ValidationError):
        EvaluationCaseCreate.model_validate(_case(origin="generated"))

    generated = EvaluationCaseCreate.model_validate(
        _case(
            origin="generated",
            source_execution=EXECUTION,
            source_revision=REVISION,
        )
    )
    assert generated.source_execution == SemanticExecutionReference.model_validate(EXECUTION)


def test_agent_is_a_supported_evaluation_target_kind() -> None:
    agent_case = EvaluationCaseCreate.model_validate(
        _case(target_kind="agent", target_key="assistant_agent")
    )
    assert agent_case.target_kind == "agent"


def test_target_name_is_required_human_display_metadata() -> None:
    with pytest.raises(ValidationError):
        EvaluationCaseCreate.model_validate(_case(target_name=" "))


def test_json_fields_have_strict_serialized_byte_limits() -> None:
    EvaluationCaseCreate.model_validate(_case(input_json={"value": "x" * (MAX_JSON_BYTES - 20)}))

    with pytest.raises(ValidationError, match="serialized JSON"):
        EvaluationCaseCreate.model_validate(_case(input_json={"value": "x" * MAX_JSON_BYTES}))


def test_completed_judgment_is_binary_and_may_omit_duration() -> None:
    result = EvaluationAttemptResult(
        status="passed",
        reason="The response names a plausible specific place.",
    )
    assert result.duration_ms is None

    with pytest.raises(ValidationError, match="Extra inputs"):
        EvaluationAttemptResult.model_validate(
            {
                "status": "passed",
                "score": 1.0,
                "reason": "The response names a plausible specific place.",
            }
        )


def test_semantic_execution_namespace_is_exact_but_normalized() -> None:
    reference = SemanticExecutionReference(
        service_namespace="",
        service_name="ai-chat-evaluation",
        executable_type="workflow",
        runtime_id="workflow-run",
    )
    assert reference.service_namespace == ""

    with pytest.raises(ValidationError, match="surrounding whitespace"):
        SemanticExecutionReference(
            service_namespace=" junjo.examples",
            service_name="ai-chat-evaluation",
            executable_type="workflow",
            runtime_id="workflow-run",
        )


def test_malformed_cursor_is_a_typed_domain_failure() -> None:
    with pytest.raises(ValueError, match="Invalid pagination cursor"):
        decode_time_cursor("runs", "____")
