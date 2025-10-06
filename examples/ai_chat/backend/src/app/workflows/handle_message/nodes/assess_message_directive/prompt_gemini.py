from app.db.models.message.schemas import MessageRead
from app.workflows.handle_message.schemas import MessageDirective


def assess_message_directive_prompt(history: list[MessageRead]) -> str:
    """Create a message response using history and contact bio information."""
    # Create the prompt
    return f"""
You are are chatting with a match in a dating app where sending photos is allowed and common.
Your task is to select the best response type for the next AI step based on the RECENT_MESSAGES below.

# RECENT_MESSAGES:
{history}

# RESPONSE_TYPE OPTIONS:
- {MessageDirective.DATE_IDEA_RESEARCH} - respond with date ideas.
- {MessageDirective.WORK_RELATED_RESPONSE} - respond about a work-related topic.
- {MessageDirective.IMAGE_RESPONSE} - respond with both an image and text.
- {MessageDirective.GENERAL_RESPONSE} - respond with just text on any other topic.

Return a single RESPONSE_TYPE from above as a string value and nothing else. No quotes or punctuation.
""".strip()
