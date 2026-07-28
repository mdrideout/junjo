"""Typed domain failures for the evaluation control plane."""

from __future__ import annotations


class EvaluationNotFoundError(LookupError):
    """Raised when one requested evaluation record does not exist."""

    def __init__(self, resource: str) -> None:
        self.resource = resource
        super().__init__(f"{resource} not found")


class EvaluationConflictError(ValueError):
    """Raised when a write conflicts with immutable or terminal state."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class EvaluationCursorError(ValueError):
    """Raised when an opaque page cursor is malformed or used on another route."""

    def __init__(self) -> None:
        super().__init__("Invalid pagination cursor")
