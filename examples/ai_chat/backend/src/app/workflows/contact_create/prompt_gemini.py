from app.db.models.contact.schemas import GenderEnum


def contact_create_prompt_gemini(schema: str, gender: GenderEnum) -> str:
    return f"""
Create a {gender.value.lower()} dating app profile.

The intent is to have a dating partner with a unique to chat with.

Adhere to the following schema for field limitations:
{schema}
""".strip()
