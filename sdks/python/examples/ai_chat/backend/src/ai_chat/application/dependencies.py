"""Request-scoped capabilities visible to chat Agent Tools."""

from dataclasses import dataclass

from ai_chat.domain.ports import ContactReader, HistoryReader, ImageRenderer


@dataclass(frozen=True, slots=True)
class ChatDependencies:
    """Authorized application capabilities for exactly one conversation turn."""

    conversation_id: str
    turn_id: str
    history: HistoryReader
    contacts: ContactReader
    images: ImageRenderer
