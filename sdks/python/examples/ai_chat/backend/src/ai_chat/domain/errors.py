"""Application-owned domain failures."""


class ConversationNotFoundError(LookupError):
    """The requested conversation does not exist."""


class ContactNotFoundError(LookupError):
    """The requested conversation has no contact profile."""


class TurnPersistenceError(RuntimeError):
    """A turn violates the application's persistence invariants."""
