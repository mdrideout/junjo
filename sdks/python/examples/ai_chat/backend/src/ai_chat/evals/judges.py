"""Small application-owned judge contracts shared by live eval datasets."""

from pydantic import BaseModel, ConfigDict, Field

from ai_chat.domain.ports import LanguageModel


class QualityJudgment(BaseModel):
    """A bounded qualitative decision made against one explicit rubric."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    reason: str = Field(min_length=1, max_length=1_000)


async def judge_text(
    *,
    language: LanguageModel,
    rubric: str,
    subject: str,
) -> QualityJudgment:
    """Judge text through the selected live provider and a closed result schema."""

    return await language.generate_structured(
        prompt=f"""
Evaluate the supplied subject against the rubric. Be strict and judge only the
evidence present. Return a binary passed decision and a concise reason.

RUBRIC:
{rubric}

SUBJECT:
{subject}
""".strip(),
        output_type=QualityJudgment,
    )
