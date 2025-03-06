from app.db.models.contact.schemas import GenderEnum


def contact_create_prompt_gemini(schema: str, gender: GenderEnum) -> str:
    return f"""
Create a realistic {gender.value.lower()} dating app profile modeled after Tinder profiles.

You will be creating many of these, so try to make this one unique.

Requirements:
- Age is at least 18 and less than 100
- Weight is over 70 lbs and under 500 lbs
- Keep the bio to under 200 tokens
- Do not abbreviate city or state

Output JSON according to the following schema:
{schema}
""".strip()
