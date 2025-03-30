from app.workflows_junjo.handle_message.schemas import MessageDirective
def assess_message_directive_prompt(most_recent_message: str) -> str:
    """Create a message response using history and contact bio information."""
    # Create the prompt
    return f"""
You are an AI chat app message analyzer. It is your job to select the most appropriate repsonse directive category for the next AI step.

You have received the following message:
{most_recent_message}

These are the response directive categories to choose from:
1. {MessageDirective.DATE_IDEA_RESEARCH} - the user wants you to suggest date ideas.
2. {MessageDirective.WORK_RELATED_RESPONSE} - the user wants you to talk about work-related topics.
3. {MessageDirective.GENERAL_RESPONSE} - anything that does not fit into the other categories.

Return the category as a string value and nothing else. No quotes or punctuation.
""".strip()
