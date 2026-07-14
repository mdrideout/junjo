"""Typed semantic failures for execution resolution."""


class ExecutionResolutionConflictError(ValueError):
    """Raised when physical evidence violates unique execution identity."""

    def __init__(self, match_count: int) -> None:
        super().__init__("Execution identity resolved to multiple owner spans.")
        self.match_count = match_count
