from app.db.models.contact.schemas import Sex
from app.workflows.create_contact.schemas import PersonalityTraits


def create_name_prompt(personality_traits: PersonalityTraits, city: str, state: str, age: int, sex: Sex) -> str:
    """Prompt to create a user name based on personality traits."""

    # Create the prompt
    return f"""
Create a name for a person based on the following information:

Traits: {personality_traits.model_dump_json()}
Location: {city}, {state}
Age: {age}
Sex: {sex}

The name should be realistic and directly relate to the traits and location provided.
Do not include the traits or location in the name.

Respond with JSON only, with the name in the format:
{{
    "first_name": "John",
    "last_name": "Doe"
}}

Output only a single definitive name. Do not be conversational or include any additional information.

The JSON output should be valid and parsable data structure. Do not include any additional information or formatting.
Do not include markdown, do not be conversational.
""".strip()
