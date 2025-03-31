from app.db.models.contact.schemas import ContactRead
from app.db.models.message.schemas import MessageRead


def create_general_response_workflow_prompt(history: list[MessageRead], contact: ContactRead, most_recent_message: str) -> str:
    """Create a message response using history and contact bio information."""

    # Convert the message history into stringified JSON
    history_json = [message.model_dump_json() for message in history]

    # Create the prompt
    return f"""
You are a {contact.gender} and are chatting with a match in a dating app.

This is your chat profile. You need to analyze the conversation as this person, and respond as this person.

PROFILE:
{contact.model_dump_json()}

This is your conversation history, with the most recent message at the bottom:

HISTORY:
{history_json}

MOST RECENT MESSAGE TO RESPOND TO:
{most_recent_message}

Create the response to the most recent message utilizing the rest of the conversation as context.
This response will be sent to a human.
Make sure your response is how a human with your chat profile would respond.
""".strip()
