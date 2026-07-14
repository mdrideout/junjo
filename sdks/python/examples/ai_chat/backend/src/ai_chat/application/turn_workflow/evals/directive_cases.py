"""Directive cases include direct and ambiguous dating-chat messages."""

from ai_chat.domain.models import MessageDirective

DIRECTIVE_CASES = (
    ("date-direct", "Suggest a fun date idea.", MessageDirective.DATE_IDEA_RESEARCH),
    ("work-direct", "What do you do for work?", MessageDirective.WORK_RELATED_RESPONSE),
    ("general-joke", "Tell me a joke.", MessageDirective.GENERAL_RESPONSE),
    ("general-casual", "What's up?", MessageDirective.GENERAL_RESPONSE),
    ("image-direct", "Can you send me a picture of what you're wearing?", MessageDirective.IMAGE_RESPONSE),
    (
        "image-contextual",
        "I'd love to see something visual related to our conversation.",
        MessageDirective.IMAGE_RESPONSE,
    ),
)
