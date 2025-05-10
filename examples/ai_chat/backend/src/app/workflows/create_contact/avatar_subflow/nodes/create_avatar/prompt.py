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
Create an ultra-realistic DSLR portrait photo of a person for a social media profile photo
based on the following information:

Traits: {personality_traits.model_dump_json()}

Bio: {bio}

Location: {city}, {state}

Use this as inspiration for the image: {inspiration}

The output image should be square, 1:1 aspect ratio, and be zoomed out enough to show any activity or context
that this person would want to show in their profile picture.

The image should be realistic and mirror what people actually do for their
profile pictures that show lifestyle and personality.
""".strip()
