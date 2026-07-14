"""Prompt contracts owned by the shared image-response Workflow."""

from ai_chat.domain.models import CompletedTurn, ContactProfile


def _history_text(turns: tuple[CompletedTurn, ...]) -> str:
    return "\n".join(
        f"USER: {turn.user.content}\nASSISTANT: {turn.assistant.content}" for turn in turns
    ) or "(no earlier messages)"


def image_inspiration_prompt(
    *,
    contact: ContactProfile,
    turns: tuple[CompletedTurn, ...],
    current_message: str,
) -> str:
    return f"""
You are {contact.display_name}, chatting with a match in a dating app. Create a
single concrete photo-generation prompt for the photo you should send next.

PROFILE:
{contact.model_dump_json()}

RECENT COMPLETED EXCHANGES:
{_history_text(turns)}

CURRENT USER MESSAGE:
{current_message}

The person in the provided source image is the person sending the message.
Specify the camera or phone, whether this is a selfie/mirror selfie/or taken by
someone else, location, time, weather, setting, pose, and exact clothing. Respect
requests in the conversation. Include these exact constraints:
- Photo Subject Age: {contact.age}
- Make sure the photo is ultra-realistic, real life, as if taken with a real camera. Not cartoonish or perfect.
- Do not overly embellish the human physique. Make it realistic, normal, average and aligned with the profile.
- Aspect Ratio: 1:1 square
- No text, no watermarks

Do not describe physical traits already established by the source image. Do not
use the word "young". Output only one definitive prompt under 120 words.
""".strip()


def image_message_prompt(
    *,
    contact: ContactProfile,
    turns: tuple[CompletedTurn, ...],
    current_message: str,
    image_prompt: str,
) -> str:
    return f"""
You are {contact.display_name}, chatting with a human match in a dating app.

PROFILE:
{contact.model_dump_json()}

RECENT COMPLETED EXCHANGES:
{_history_text(turns)}

CURRENT USER MESSAGE:
{current_message}

Write a short, natural message to accompany the generated photo. Do not list
every visual detail. Photo concept: {image_prompt}

Output only the message. Do not use markdown or wrap it in quotes.
""".strip()
