"""Deliberate live directive eval; excluded from the ordinary test suite."""

from datetime import UTC, datetime
from time import perf_counter

import pytest
from junjo import ExecutionCorrelation, evaluate_node

from ai_chat.application.turn_workflow.nodes import AssessMessageDirectiveNode
from ai_chat.application.turn_workflow.state import TurnWorkflowState, TurnWorkflowStore
from ai_chat.domain.models import (
    ChatMessage,
    ContextPolicyReference,
    MessageDirective,
    MessageRole,
    Turn,
    TurnStatus,
)
from ai_chat.evals.provider import live_language_model, provider_identity
from ai_chat.evals.results import EvalResult, EvalResultRecorder, studio_execution_url

from .directive_cases import DIRECTIVE_CASES

pytestmark = pytest.mark.live_eval


@pytest.mark.parametrize(("case_id", "message", "expected"), DIRECTIVE_CASES, ids=[case[0] for case in DIRECTIVE_CASES])
async def test_directive_selection(
    case_id: str,
    message: str,
    expected: MessageDirective,
    live_telemetry: object,
) -> None:
    del live_telemetry
    async with live_language_model() as (settings, language):
        now = datetime.now(UTC)
        turn = Turn(
            id=f"turn-{case_id}",
            revision=1,
            conversation_id="eval-conversation",
            sequence=1,
            status=TurnStatus.RUNNING,
            context_policy=ContextPolicyReference(),
            user_message=ChatMessage(
                id=f"message-{case_id}",
                turn_id=f"turn-{case_id}",
                conversation_id="eval-conversation",
                role=MessageRole.USER,
                content=message,
                created_at=now,
            ),
            created_at=now,
            updated_at=now,
        )
        started = perf_counter()
        result = await evaluate_node(
            node=AssessMessageDirectiveNode(language),
            store=TurnWorkflowStore(initial_state=TurnWorkflowState(turn=turn)),
            correlation=ExecutionCorrelation(type="ai_chat.eval_case", id=case_id),
        )
        duration_ms = round((perf_counter() - started) * 1_000)
        passed = result.state.directive is expected
        reason = (
            f"Expected {expected.value}; received "
            f"{result.state.directive.value if result.state.directive is not None else 'no directive'}."
        )
        identity = provider_identity(settings)
        artifact = EvalResultRecorder(settings.database_path.parent / "eval-results").record(
            EvalResult(
                dataset_id="turn-directive-selection",
                dataset_version="1",
                case_id=case_id,
                capability="turn.directive_selection",
                prompt_version="directive-v1",
                provider=identity.provider,
                model=identity.model,
                executable_type="workflow",
                run_id=result.run_id,
                passed=passed,
                score=1.0 if passed else 0.0,
                reason=reason,
                duration_ms=duration_ms,
                studio_url=studio_execution_url(
                    settings.debug,
                    executable_type="workflow",
                    run_id=result.run_id,
                ),
            )
        )
        print(artifact)
        assert passed, f"run_id={result.run_id}: expected {expected}, received {result.state.directive}"
