"""Prompt contracts for the model-powered contact creation Workflow."""

from ai_chat.domain.models import ContactSex, PersonalityTraits


def location_prompt(latitude: float, longitude: float) -> str:
    return f"""
Return the nearest real city and US state for these coordinates:
latitude={latitude}, longitude={longitude}.

Return the city and two-letter state abbreviation through the requested schema.
""".strip()


def biography_prompt(
    *,
    personality: PersonalityTraits,
    city: str,
    state: str,
    age: int,
    sex: ContactSex,
) -> str:
    return f"""
Create a realistic dating profile biography for this person:

Personality traits: {personality.model_dump_json()}
Location: {city}, {state}
Age: {age}
Sex: {sex.value}

Ground the biography in those facts without listing trait scores. Include personal
history, hobbies, a specific job title and employer, family/relationship status,
and interests. Establish details that can support a coherent continuing personal
narrative in later conversations.

Output one definitive biography under 250 words. Do not use markdown, quote the
answer, or add commentary.
""".strip()


def name_prompt(
    *,
    personality: PersonalityTraits,
    city: str,
    state: str,
    age: int,
    sex: ContactSex,
) -> str:
    return f"""
Create one realistic name for this person:

Personality traits: {personality.model_dump_json()}
Location: {city}, {state}
Age: {age}
Sex: {sex.value}

Return first_name and last_name through the requested schema. Do not add
commentary or include the input facts in the name.
""".strip()


def avatar_inspiration_prompt(
    *,
    personality: PersonalityTraits,
    bio: str,
    city: str,
    state: str,
    first_name: str,
    last_name: str,
) -> str:
    return f"""
Create one realistic photography idea for a dating-profile picture for:

Name: {first_name} {last_name}
Location: {city}, {state}
Personality traits: {personality.model_dump_json()}
Biography: {bio}

Use at most one hobby or interest as the setting. Keep the person's head clearly
visible. Do not include books or eating. Output one definitive idea under 50 words
without commentary.
""".strip()


def avatar_generation_prompt(
    *,
    personality: PersonalityTraits,
    bio: str,
    city: str,
    state: str,
    sex: ContactSex,
    age: int,
    inspiration: str,
) -> str:
    return f"""
Create an ultra-realistic iPhone-quality dating profile photo for this person:

Personality traits: {personality.model_dump_json()}
Biography: {bio}
Location: {city}, {state}
Sex: {sex.value}
Age: {age}
Photography concept: {inspiration}

The image must be square (1:1). The face must be clearly visible and occupy at
least 30 percent of the image. Make this look like a normal real-life profile
photo, not a polished illustration. No text or watermarks.
""".strip()
