"""Application-boundary tests for AI Chat's public Junjo harness declaration."""

import pytest
from junjo.studio import TargetKind

from ai_chat.evals.harness import (
    APPLICATION_KEY,
    CHAT_AGENT_TARGET,
    DATE_RESPONSE_NODE_TARGET,
    LOCAL_PLACE_INPUT_VERSION,
    TEXT_QUALITY_EVALUATOR,
    TEXT_QUALITY_EVALUATOR_VERSION,
    TURN_WORKFLOW_TARGET,
    authored_local_place_input,
    harness,
    text_quality_expectation,
)


def test_harness_lists_node_workflow_and_agent_without_runtime_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("JUNJO_AI_STUDIO_API_KEY", raising=False)

    descriptors = harness.target_descriptors()

    assert harness.application_key == APPLICATION_KEY
    assert harness.service_identity.service_namespace == "junjo.examples"
    assert harness.service_identity.service_name == "ai-chat"
    assert [(descriptor.kind, descriptor.key, descriptor.input_version) for descriptor in descriptors] == [
        (TargetKind.AGENT, CHAT_AGENT_TARGET, LOCAL_PLACE_INPUT_VERSION),
        (TargetKind.NODE, DATE_RESPONSE_NODE_TARGET, LOCAL_PLACE_INPUT_VERSION),
        (TargetKind.WORKFLOW, TURN_WORKFLOW_TARGET, LOCAL_PLACE_INPUT_VERSION),
    ]
    assert all(descriptor.input_schema["additionalProperties"] is False for descriptor in descriptors)


@pytest.mark.parametrize(
    ("target_kind", "target_key"),
    [
        (TargetKind.NODE, DATE_RESPONSE_NODE_TARGET),
        (TargetKind.WORKFLOW, TURN_WORKFLOW_TARGET),
        (TargetKind.AGENT, CHAT_AGENT_TARGET),
    ],
)
def test_all_targets_share_the_explicit_local_place_contract(
    target_kind: TargetKind,
    target_key: str,
) -> None:
    _, input_value, _, expectation = harness.validate_case_contract(
        target_kind=target_kind,
        target_key=target_key,
        input_version=LOCAL_PLACE_INPUT_VERSION,
        input_json=authored_local_place_input("  Find a believable neighborhood place.  "),
        evaluator_key=TEXT_QUALITY_EVALUATOR,
        evaluator_version=TEXT_QUALITY_EVALUATOR_VERSION,
        expectation_json=text_quality_expectation("  Prefer specific, real local detail.  "),
    )

    assert input_value.message == "Find a believable neighborhood place."
    assert expectation.rubric == "Prefer specific, real local detail."


def test_invalid_case_contract_fails_before_resources_or_provider_work() -> None:
    with pytest.raises(ValueError, match="Input does not match target"):
        harness.validate_case_contract(
            target_kind=TargetKind.NODE,
            target_key=DATE_RESPONSE_NODE_TARGET,
            input_version=LOCAL_PLACE_INPUT_VERSION,
            input_json={"message": "   "},
            evaluator_key=TEXT_QUALITY_EVALUATOR,
            evaluator_version=TEXT_QUALITY_EVALUATOR_VERSION,
            expectation_json=text_quality_expectation("Use real places."),
        )
