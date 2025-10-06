import random

from pydantic import BaseModel, Field


class PersonalityTraits(BaseModel):
    """Normalized scores (0‑1) for the Big‑Five personality dimensions."""

    openness: float = Field(..., ge=0.0, le=1.0)
    conscientiousness: float = Field(..., ge=0.0, le=1.0)
    extraversion: float = Field(..., ge=0.0, le=1.0)
    agreeableness: float = Field(..., ge=0.0, le=1.0)
    neuroticism: float = Field(..., ge=0.0, le=1.0)
    intelligence: float = Field(..., ge=0.0, le=1.0)
    religiousness: float = Field(..., ge=0.0, le=1.0)
    attractiveness: float = Field(..., ge=0.0, le=1.0)
    trauma: float = Field(..., ge=0.0, le=1.0)

    @staticmethod
    def generate_random() -> "PersonalityTraits":
        rng = random
        return PersonalityTraits(
            openness=round(rng.betavariate(5, 2), 2),
            conscientiousness=round(rng.uniform(0.0, 1.0), 2),
            extraversion=round(rng.betavariate(5, 2), 2),
            agreeableness=round(rng.betavariate(5, 2), 2),
            neuroticism=round(rng.uniform(0.0, 1.0), 2),
            intelligence=round(rng.uniform(0.0, 1.0), 2),
            religiousness=round(rng.betavariate(2, 5), 2),
            attractiveness=round(rng.betavariate(9, 2), 2),
            trauma=round(rng.betavariate(2, 5), 2),
        )
