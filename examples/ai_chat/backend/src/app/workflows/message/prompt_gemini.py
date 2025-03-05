from app.db.models.contact.schemas import GenderEnum


def message_response_prompt_gemini(message: str, gender: GenderEnum) -> str:
    return f"""
You are a {gender} and are chatting with a match in a dating app.

This is the most recent message you have received from your match:
{message}

Create a response. This response will be sent to the human. Make sure it is how a human {gender} would respond.
""".strip()
