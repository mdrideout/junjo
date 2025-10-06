from app.workflows.create_contact.schemas import PersonalityTraits


def avatar_inspiration_prompt(
    personality_traits: PersonalityTraits, bio: str, city: str, state: str, first_name: str, last_name: str
) -> str:
    """Creates an image prompt to inspire the avatar that will be generated."""

    # Create the prompt
    return f"""
Your job is to come up with a fun photography idea prompt for a social media profile picture for this person:

Name: {first_name} {last_name}

Location: {city}, {state}

Traits: {personality_traits.model_dump_json()}

Bio: {bio}

Output a single idea in under 50 words. Be realistic and mirror what people actually do
for their profile pictures that show lifestyle and personality. If they have hobbies or interests
in their bio, select only one to include as the setting for the photography prompt.

Do not include the name, location, or traits, or bio in the prompt. Do not include any additional information.
Do not be conversational, just output a single definitive photography idea prompt.
Do not include books in the idea. Do not be eating.

Ensure the person's head is visible in the image.
""".strip()
