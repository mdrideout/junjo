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


class ImageEditRefusedError(RuntimeError):
    """An image provider returned a safe text refusal instead of an image."""

    def __init__(self, *, provider: str, reason: str) -> None:
        self.provider = provider
        self.reason = reason.strip()
        if not self.reason:
            raise ValueError("Image edit refusal reason cannot be blank.")
        super().__init__(f"{provider} declined to edit the image: {self.reason}")


class TurnExecutionError(RuntimeError):
    """A Turn reached a durable failed state during execution."""

    def __init__(
        self,
        turn_id: str,
        detail: str = "Turn execution failed.",
        *,
        workflow_run_id: str | None = None,
        agent_run_id: str | None = None,
    ) -> None:
        self.turn_id = turn_id
        self.workflow_run_id = workflow_run_id
        self.agent_run_id = agent_run_id
        super().__init__(detail)
