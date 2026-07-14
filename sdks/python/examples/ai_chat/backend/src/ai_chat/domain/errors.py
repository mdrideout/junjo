"""Application-owned domain failures."""


class ConversationNotFoundError(LookupError):
    """The requested conversation does not exist."""


class ContactNotFoundError(LookupError):
    """The requested conversation has no contact profile."""


class TurnPersistenceError(RuntimeError):
    """A turn violates the application's persistence invariants."""


class TurnInProgressError(RuntimeError):
    """A conversation already has an admitted or running Turn."""

    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"Conversation {conversation_id} already has an active Turn.")


class TurnNotFoundError(LookupError):
    """The requested Turn does not exist."""

    def __init__(self, turn_id: str) -> None:
        self.turn_id = turn_id
        super().__init__(f"Turn {turn_id} does not exist.")


class TurnExecutionError(RuntimeError):
    """A Turn reached a durable failed state during execution."""

    def __init__(self, turn_id: str, detail: str = "Turn execution failed.") -> None:
        self.turn_id = turn_id
        super().__init__(detail)
