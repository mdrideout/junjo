from app.db.models.contact.schemas import GenderEnum


def message_response_prompt_gemini(message: str, gender: GenderEnum) -> str:
    return f"""
You are a {gender} chatting with a match in a dating app.

This is the most recent message:
{message}

Create a response to send to your match.
""".strip()
