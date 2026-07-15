"""Biography quality rubric and typed live judge."""

from pydantic import BaseModel, ConfigDict, Field

from ai_chat.domain.models import ContactSex, PersonalityTraits
from ai_chat.domain.ports import LanguageModel


class BiographyJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=1_000)


async def judge_biography(
    *,
    language: LanguageModel,
    bio: str,
    personality: PersonalityTraits,
    age: int,
    sex: ContactSex,
    city: str,
    state: str,
) -> BiographyJudgment:
    prompt = f"""
Evaluate this generated dating-profile biography.

INPUT FACTS:
age={age}, sex={sex.value}, location={city}, {state}
personality={personality.model_dump_json()}

CANDIDATE BIOGRAPHY:
{bio}

Pass only when the biography is realistic, internally consistent, under 250
words, grounded in the input without exposing numeric trait scores, and includes
personal history, hobbies/interests, a specific job title and employer, and
family/relationship status. Reject stereotypes, contradictions, unsafe age
implications, markdown, or meta-commentary. Return passed, a score from 0 to 1,
and a concise reason through the requested schema.
""".strip()
    return await language.generate_structured(prompt=prompt, output_type=BiographyJudgment)
