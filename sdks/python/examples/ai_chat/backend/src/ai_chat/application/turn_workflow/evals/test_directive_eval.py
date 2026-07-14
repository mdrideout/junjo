"""Deliberate live directive eval; excluded from the ordinary test suite."""

from datetime import UTC, datetime

import pytest
from junjo import ExecutionCorrelation, evaluate_node

from ai_chat.application.turn_workflow.nodes import AssessMessageDirectiveNode
from ai_chat.application.turn_workflow.state import TurnWorkflowState, TurnWorkflowStore
from ai_chat.domain.models import ChatMessage, ContextPolicyReference, MessageRole, Turn, TurnStatus
from ai_chat.evals.provider import live_language_model

from .directive_cases import DIRECTIVE_CASES

pytestmark = pytest.mark.live_eval


@pytest.mark.parametrize(("case_id", "message", "expected"), DIRECTIVE_CASES, ids=[case[0] for case in DIRECTIVE_CASES])
async def test_directive_selection(
    case_id: str,
    message: str,
    expected: object,
    live_telemetry: object,
) -> None:
    del live_telemetry
    _, language = live_language_model()
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
    result = await evaluate_node(
        node=AssessMessageDirectiveNode(language),
        store=TurnWorkflowStore(initial_state=TurnWorkflowState(turn=turn)),
        correlation=ExecutionCorrelation(type="ai_chat.eval_case", id=case_id),
    )
    assert result.state.directive is expected, (
        f"run_id={result.run_id}: expected {expected}, received {result.state.directive}"
    )
