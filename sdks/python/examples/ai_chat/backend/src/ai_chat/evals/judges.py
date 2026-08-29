"""Small application-owned judge contracts shared by live eval datasets."""

from pydantic import BaseModel, ConfigDict, Field

from ai_chat.domain.ports import LanguageModel
from ai_chat.evals.local_places import RecommendedPlaceClaim


class QualityJudgment(BaseModel):
    """A bounded qualitative decision made against one explicit rubric."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    reason: str = Field(min_length=1, max_length=1_000)


class LocalPlaceQualityJudgment(BaseModel):
    """Qualitative result plus literal venue claims for deterministic checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    reason: str = Field(min_length=1, max_length=1_000)
    places: tuple[RecommendedPlaceClaim, ...]


async def judge_text(
    *,
    language: LanguageModel,
    rubric: str,
    subject: str,
) -> QualityJudgment:
    """Judge text through the selected live provider and a closed result schema."""

    return await language.generate_structured(
        prompt=f"""
Evaluate the supplied subject against the rubric. Judge only the evidence
present; do not assume current facts that are not supplied. Return a binary
passed decision and a concise reason that names the deciding rubric condition
and the exact observation that satisfied or violated it.

RUBRIC:
{rubric}

SUBJECT:
{subject}
""".strip(),
        output_type=QualityJudgment,
    )


async def judge_local_place_text(
    *,
    language: LanguageModel,
    rubric: str,
    subject: str,
) -> LocalPlaceQualityJudgment:
    """Judge observable quality and transcribe every recommended venue claim."""

    return await language.generate_structured(
        prompt=f"""
Evaluate the supplied subject against the rubric. Judge only qualitative
conditions observable in the response; a separate deterministic verifier owns
whether a place exists, operates, or is correctly located. Return a binary
passed decision and a concise reason naming the deciding qualitative condition.

Also extract every specific venue that the ASSISTANT RESPONSE positively
recommends, including alternatives. Preserve each venue's stated name. Copy a
street or address only when the response explicitly attaches it to that venue.
Copy a neighborhood only when the response explicitly says the venue is in
that neighborhood. Do not infer, correct, omit, or add place facts. Return an
empty places list when no specific venue is recommended.

RUBRIC:
{rubric}

SUBJECT:
{subject}
""".strip(),
        output_type=LocalPlaceQualityJudgment,
    )
