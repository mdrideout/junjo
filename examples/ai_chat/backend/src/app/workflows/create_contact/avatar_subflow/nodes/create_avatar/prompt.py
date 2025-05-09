from app.workflows.create_contact.schemas import PersonalityTraits


def create_avatar_prompt(
    personality_traits: PersonalityTraits,
    bio: str,
    city: str,
    state: str,
    inspiration: str
) -> str:
    """Prompt to generate an avatar image based on the provided information."""

    # Create the prompt
    return f"""
Create an ultra-realistic DSLR portrait photo of a person for a dating app profile based on the following information:

Traits: {personality_traits.model_dump_json()}
Bio: {bio}
Location: {city}, {state}

The output image should be square, 1:1 aspect ratio, and show a lot of background detail.

Use this as inspiration for the image: {inspiration}
""".strip()
