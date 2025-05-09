from app.workflows.create_contact.schemas import PersonalityTraits


def avatar_inspiration_prompt(
        personality_traits: PersonalityTraits,
          bio: str,
          city: str,
          state: str,
          first_name: str,
          last_name: str
        ) -> str:
    """Creates an image prompt to inspire the avatar that will be generated."""

    # Create the prompt
    return f"""
Your job is to come up with a fun photography idea for a social media profile picture for this person:

Name: {first_name} {last_name}
Traits: {personality_traits.model_dump_json()}
Bio: {bio}
Location: {city}, {state}

Output a single idea in under 50 words. Be realistic and mirror what people actually do
for their profile pictures that show lifestyle and personality.

Do not be conversational, just output a single definitive idea.

""".strip()
