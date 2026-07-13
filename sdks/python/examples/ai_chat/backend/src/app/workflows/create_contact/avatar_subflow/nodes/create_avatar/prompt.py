from app.db.models.contact.schemas import Sex
from app.workflows.create_contact.schemas import PersonalityTraits


def create_avatar_prompt(
    personality_traits: PersonalityTraits, bio: str, city: str, state: str, sex: Sex, inspiration: str
) -> str:
    """Prompt to generate an avatar image based on the provided information."""

    # Create the prompt
    return f"""
Create an ultra-realistic iphone-quality photo of a person for a dating profile photo
based on the following information:

Traits: {personality_traits.model_dump_json()}

Bio: {bio}

Location: {city}, {state}

Sex: {sex}

Use this as inspiration for the image: {inspiration}

The output image should be square, 1:1 aspect ratio.
The face should be clearly visible and taking up at least 30% of the image.
The image should be realistic and mirror what people actually do for their profile pictures.
Do not include watermarks in the image.
""".strip()
