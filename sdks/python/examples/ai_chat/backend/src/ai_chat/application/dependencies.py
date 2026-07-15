"""Request-scoped capabilities visible to chat Agent Tools."""

from dataclasses import dataclass

from ai_chat.domain.models import CompletedTurn, ContactProfile
from ai_chat.domain.ports import HistoryReader, ImageModel, LanguageModel


@dataclass(frozen=True, slots=True)
class ChatDependencies:
    """Authorized application capabilities for exactly one conversation turn."""

    conversation_id: str
    turn_id: str
    before_sequence: int
    contact: ContactProfile
    recent_turns: tuple[CompletedTurn, ...]
    history: HistoryReader
    language: LanguageModel
    images: ImageModel
