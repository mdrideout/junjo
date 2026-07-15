"""Prompt contracts for message classification and persona-aware responses."""

from ai_chat.domain.models import CompletedTurn, ContactProfile, MessageDirective


def _history_json(turns: tuple[CompletedTurn, ...]) -> str:
    return (
        "\n".join((f"USER: {turn.user.content}\nASSISTANT: {turn.assistant.content}") for turn in turns)
        or "(no earlier messages)"
    )


def directive_prompt(*, turns: tuple[CompletedTurn, ...], current_message: str) -> str:
    return f"""
You are classifying the next response in a dating-app conversation where sending
photos is allowed and common.

RECENT COMPLETED EXCHANGES:
{_history_json(turns)}

CURRENT USER MESSAGE:
{current_message}

Choose exactly one directive through the requested schema:
- {MessageDirective.DATE_IDEA_RESEARCH.value}: the user wants date ideas or concrete places.
- {MessageDirective.WORK_RELATED_RESPONSE.value}: the conversation is about the contact's work.
- {MessageDirective.IMAGE_RESPONSE.value}: a photo is requested or would clearly be the best response.
- {MessageDirective.GENERAL_RESPONSE.value}: ordinary text conversation.
""".strip()


def persona_response_prompt(
    *,
    contact: ContactProfile,
    turns: tuple[CompletedTurn, ...],
    current_message: str,
    directive: str,
) -> str:
    return f"""
You are {contact.display_name}, chatting with a human match in a dating app.
Respond as this person, preserving a coherent personal narrative.

PROFILE:
{contact.model_dump_json()}

RECENT COMPLETED EXCHANGES:
{_history_json(turns)}

CURRENT USER MESSAGE:
{current_message}

RESPONSE DIRECTIVE:
{directive}

Write only the message that should be sent. Sound like a real person. Do not use
markdown or wrap the response in quotes.
""".strip()
