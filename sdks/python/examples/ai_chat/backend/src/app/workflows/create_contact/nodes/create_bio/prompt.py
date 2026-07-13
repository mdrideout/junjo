from app.db.models.contact.schemas import Sex
from app.workflows.create_contact.schemas import PersonalityTraits


def create_bio_prompt(personality_traits: PersonalityTraits, city: str, state: str, age: int, sex: Sex) -> str:
    """Prompt to create a user bio based on personality traits."""

    # Create the prompt
    return f"""
Create a short dating profile bio for a person based on the following information:

Traits: {personality_traits.model_dump_json()}
Location: {city}, {state}
Age: {age}
Sex: {sex}

The bio should be realistic and directly relate to the traits and location provided.
Do not include the traits or location in the bio.

Include the following:
- Some personal history
- Hobbies
- Work (a specific job title and employer)
- Family status (kids, spouse, single, divorced, etc.)
- Interests

Output only a single definitive bio in under 250 words. Do not be conversational or include any additional information.

This output will be directly inserted into the user's profile.
""".strip()
