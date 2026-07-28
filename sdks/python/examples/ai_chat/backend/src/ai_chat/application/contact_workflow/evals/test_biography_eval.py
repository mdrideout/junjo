"""Deliberate live biography eval; excluded from the ordinary test suite."""

import pytest
from junjo import ExecutionCorrelation, evaluate_node

from ai_chat.application.contact_workflow.nodes import CreateBioNode
from ai_chat.application.contact_workflow.state import ContactWorkflowState, ContactWorkflowStore
from ai_chat.domain.models import ContactSex, PersonalityTraits
from ai_chat.evals.provider import live_language_model

from .biography_cases import BIOGRAPHY_CASES
from .biography_judge import judge_biography

pytestmark = pytest.mark.live_eval


@pytest.mark.parametrize("case", BIOGRAPHY_CASES, ids=lambda case: case["id"])
async def test_biography_quality(case: dict[str, object], live_telemetry: object) -> None:
    del live_telemetry
    async with live_language_model() as (_settings, language):
        personality = PersonalityTraits.model_validate(case["personality"])
        sex = ContactSex(str(case["sex"]))
        state = ContactWorkflowState(
            contact_id=f"eval-{case['id']}",
            conversation_id=f"eval-{case['id']}",
            sex=sex,
            age=int(str(case["age"])),
            latitude=0,
            longitude=0,
            city=str(case["city"]),
            state=str(case["state"]),
            personality=personality,
        )
        result = await evaluate_node(
            node=CreateBioNode(language),
            store=ContactWorkflowStore(initial_state=state),
            correlation=ExecutionCorrelation(type="ai_chat.eval_case", id=str(case["id"])),
        )
        assert result.state.bio is not None
        judgment = await judge_biography(
            language=language,
            bio=result.state.bio,
            personality=personality,
            age=state.age or 0,
            sex=sex,
            city=state.city or "",
            state=state.state or "",
        )
        assert judgment.passed, f"run_id={result.run_id}: {judgment.reason}"
