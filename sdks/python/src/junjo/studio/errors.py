"""Typed failures raised by :mod:`junjo.studio`."""

from __future__ import annotations

from .models import (
    ExecutionEvidenceReference,
    ExecutionResolutionConflict,
    SemanticExecutionReference,
)


class StudioError(RuntimeError):
    """Base class for all Studio client and projection failures."""


class StudioAuthenticationError(StudioError):
    """Studio rejected the configured session or control/query token."""


class StudioAuthorizationError(StudioAuthenticationError):
    """Authenticated Studio authority lacks a required operation scope."""


class StudioValidationError(StudioError):
    """Studio rejected a request that passed local SDK validation."""

    def __init__(self, *, method: str, path: str) -> None:
        self.method = method
        self.path = path
        super().__init__(f"Studio rejected the {method} {path} request as invalid.")


class StudioConflictError(StudioError):
    """An idempotent mutation conflicts with already stored immutable content."""

    def __init__(
        self,
        *,
        method: str,
        path: str,
        code: str,
        detail: str,
    ) -> None:
        self.method = method
        self.path = path
        self.code = code
        self.detail = detail
        super().__init__(f"Studio rejected {method} {path} with conflict {code}.")


class StudioContractError(StudioError):
    """Studio returned content that does not match the supported API contract."""


class StudioResponseTooLargeError(StudioContractError):
    """A response exceeded the SDK's configured byte budget."""

    def __init__(self, *, path: str, max_bytes: int) -> None:
        self.path = path
        self.max_bytes = max_bytes
        super().__init__(f"Studio response for {path} exceeded the {max_bytes}-byte limit.")


class StudioRequestError(StudioError):
    """Studio returned a non-success response with no more specific meaning."""

    def __init__(self, *, method: str, path: str, status_code: int) -> None:
        self.method = method
        self.path = path
        self.status_code = status_code
        super().__init__(f"Studio returned HTTP {status_code} for {method} {path}.")


class StudioTransientError(StudioError):
    """A retryable transport or availability failure exhausted its attempts."""

    def __init__(
        self,
        *,
        method: str,
        path: str,
        status_code: int | None,
    ) -> None:
        self.method = method
        self.path = path
        self.status_code = status_code
        if status_code is None:
            message = f"Studio was unavailable while sending {method} {path}."
        else:
            message = f"Studio remained unavailable with HTTP {status_code} for {method} {path}."
        super().__init__(message)


class ExecutionEvidencePending(StudioError):
    """Studio has not received or indexed one execution evidence record yet."""

    def __init__(self, evidence: ExecutionEvidenceReference) -> None:
        self.evidence = evidence
        super().__init__("Studio has not received or indexed this execution yet.")


class ExecutionIdentityAmbiguous(StudioError):
    """More than one owner span matches a supposedly exact semantic identity."""

    def __init__(
        self,
        execution: SemanticExecutionReference,
        conflict: ExecutionResolutionConflict,
    ) -> None:
        self.execution = execution
        self.conflict = conflict
        super().__init__(f"Studio found {conflict.match_count} executions for the supplied semantic identity.")


class AttemptEvidenceUnavailable(StudioError):
    """An evaluation attempt has not been bound to subject evidence."""

    def __init__(self, attempt_id: str) -> None:
        self.attempt_id = attempt_id
        super().__init__(f"Evaluation attempt {attempt_id} has no bound evidence.")


class RunComparisonError(StudioError):
    """Two evaluation runs cannot be paired by exact locked case membership."""
