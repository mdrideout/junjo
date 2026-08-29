"""Application-boundary tests for AI Chat's public Junjo harness declaration."""

import pytest
from junjo.studio import TargetKind

from ai_chat.application.chat_agent.definition import CHAT_AGENT_NAME
from ai_chat.application.turn_workflow.factory import TURN_WORKFLOW_NAME
from ai_chat.application.turn_workflow.nodes import CreateDateIdeaResponseNode
from ai_chat.evals.harness import (
    APPLICATION_KEY,
    CHAT_AGENT_TARGET,
    DATE_RESPONSE_NODE_TARGET,
    LOCAL_PLACE_INPUT_VERSION,
    LOCAL_PLACE_QUALITY_EVALUATOR,
    LOCAL_PLACE_QUALITY_EVALUATOR_VERSION,
    TEXT_QUALITY_EVALUATOR,
    TEXT_QUALITY_EVALUATOR_VERSION,
    TURN_WORKFLOW_TARGET,
    LocalPlaceInputV1,
    LocalPlaceQualityExpectationV1,
    TextQualityExpectationV1,
    authored_local_place_input,
    harness,
    local_place_quality_expectation,
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
    assert [
        (descriptor.kind, descriptor.key, descriptor.name, descriptor.input_version)
        for descriptor in descriptors
    ] == [
        (TargetKind.AGENT, CHAT_AGENT_TARGET, CHAT_AGENT_NAME, LOCAL_PLACE_INPUT_VERSION),
        (
            TargetKind.NODE,
            DATE_RESPONSE_NODE_TARGET,
            CreateDateIdeaResponseNode.__name__,
            LOCAL_PLACE_INPUT_VERSION,
        ),
        (TargetKind.WORKFLOW, TURN_WORKFLOW_TARGET, TURN_WORKFLOW_NAME, LOCAL_PLACE_INPUT_VERSION),
    ]
    assert all(descriptor.input_schema["additionalProperties"] is False for descriptor in descriptors)

    evaluators = harness.evaluator_descriptors()
    assert [(descriptor.key, descriptor.version) for descriptor in evaluators] == [
        (LOCAL_PLACE_QUALITY_EVALUATOR, LOCAL_PLACE_QUALITY_EVALUATOR_VERSION),
        (TEXT_QUALITY_EVALUATOR, TEXT_QUALITY_EVALUATOR_VERSION),
    ]
    assert all(
        descriptor.expectation_schema["additionalProperties"] is False
        for descriptor in evaluators
    )


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

    assert isinstance(input_value, LocalPlaceInputV1)
    assert isinstance(expectation, TextQualityExpectationV1)
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


def test_local_place_contract_combines_current_facts_and_qualitative_rubric() -> None:
    _, _, _, expectation = harness.validate_case_contract(
        target_kind=TargetKind.NODE,
        target_key=DATE_RESPONSE_NODE_TARGET,
        input_version=LOCAL_PLACE_INPUT_VERSION,
        input_json=authored_local_place_input("Find a current Prospect Heights place."),
        evaluator_key=LOCAL_PLACE_QUALITY_EVALUATOR,
        evaluator_version=LOCAL_PLACE_QUALITY_EVALUATOR_VERSION,
        expectation_json=local_place_quality_expectation(
            "The recommendation must suit a low-key first date.",
            verified_place_ids=("gold-star-beer-counter", "bierwax"),
        ),
    )

    assert isinstance(expectation, LocalPlaceQualityExpectationV1)
    assert expectation.rubric == "The recommendation must suit a low-key first date."
    assert expectation.verified_place_ids == ("gold-star-beer-counter", "bierwax")
    assert expectation.minimum_verified_places == 1


def test_local_place_contract_rejects_unknown_or_impossible_snapshot() -> None:
    with pytest.raises(ValueError, match="Unknown verified place IDs"):
        local_place_quality_expectation(
            "Use a real place.",
            verified_place_ids=("not-in-the-snapshot",),
        )

    with pytest.raises(ValueError, match="cannot exceed"):
        local_place_quality_expectation(
            "Use two real places.",
            verified_place_ids=("corto",),
            minimum_verified_places=2,
        )
