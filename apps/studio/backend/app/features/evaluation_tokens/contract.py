"""Typed internal failures for evaluation-control tokens."""


class EvaluationTokenCursorError(ValueError):
    """Raised when an evaluation-token list cursor is malformed."""


class EvaluationTokenAuthenticationError(ValueError):
    """Raised when a bearer token cannot be authenticated."""


class EvaluationTokenAuthorizationError(ValueError):
    """Raised when an authenticated token lacks a required scope."""

    def __init__(self, missing_scopes: frozenset[str]) -> None:
        self.missing_scopes = missing_scopes
        super().__init__("Evaluation token lacks the required scope.")
