"""Typed Agent construction, invocation, and execution failures."""

from __future__ import annotations

from .._json import freeze_json, require_ijson_integer, require_ijson_text
from .json import FrozenJsonValue
from .state import AgentStateSnapshot


class AgentConfigurationError(ValueError):
    """Base for invalid reusable Agent definitions; no run was created."""


class ModelDriverConfigurationError(AgentConfigurationError):
    """The declared ModelDriver binding is invalid."""


class ToolConfigurationError(AgentConfigurationError):
    """A declared Tool is invalid."""


class AgentError(Exception):
    """Base for typed failures tied to one Agent invocation identity."""

    termination_reason: str

    def __init__(
        self,
        message: str,
        *,
        agent_key: str,
        definition_id: str,
        structural_id: str,
        run_id: str,
        evidence: object = None,
    ) -> None:
        message = require_ijson_text(message, "Agent error message", nonempty=True)
        super().__init__(message)
        self.agent_key = require_ijson_text(agent_key, "agent_key", nonempty=True)
        self.definition_id = require_ijson_text(
            definition_id, "definition_id", nonempty=True
        )
        self.structural_id = require_ijson_text(
            structural_id, "structural_id", nonempty=True
        )
        self.run_id = require_ijson_text(run_id, "run_id", nonempty=True)
        self.evidence: FrozenJsonValue | AgentStateSnapshot | None = (
            evidence
            if isinstance(evidence, AgentStateSnapshot) or evidence is None
            else freeze_json(evidence)
        )


class AgentInvocationError(AgentError):
    """Boundary rejection before a run-local Store or public lifecycle exists."""


class AgentAdmissionError(AgentInvocationError):
    """Internal failure while preparing a validated invocation for admission."""

    termination_reason = "internal_error"


class AgentExecutionError(AgentError):
    """Failure after an Agent run was admitted."""

    def __init__(self, *args, state: AgentStateSnapshot, **kwargs) -> None:
        if not isinstance(state, AgentStateSnapshot):
            raise TypeError("state must be AgentStateSnapshot.")
        super().__init__(*args, evidence=state, **kwargs)
        self.state = state


class AgentInternalError(AgentExecutionError):
    """Unexpected failure inside Junjo-owned admitted runtime machinery."""

    termination_reason = "internal_error"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.superseded_outcome: str | None = None
        self.superseded_error: AgentExecutionError | None = None
        self.superseded_cancellation: BaseException | None = None


class AgentInputValidationError(AgentInvocationError):
    termination_reason = "input_validation_error"


class AgentHistoryValidationError(AgentInvocationError):
    termination_reason = "history_validation_error"


class AgentLimitExceededError(AgentExecutionError):
    termination_reason = "limit_exceeded"

    def __init__(
        self,
        *args,
        limit_kind: str,
        limit: int,
        attempted_count: int,
        requested_batch_size: int | None = None,
        **kwargs,
    ) -> None:
        require_ijson_text(limit_kind, "limit_kind", nonempty=True)
        require_ijson_integer(limit, "limit", minimum=1)
        require_ijson_integer(attempted_count, "attempted_count", minimum=1)
        if requested_batch_size is not None:
            require_ijson_integer(
                requested_batch_size, "requested_batch_size", minimum=1
            )
        super().__init__(*args, **kwargs)
        self.limit_kind = limit_kind
        self.limit = limit
        self.attempted_count = attempted_count
        self.requested_batch_size = requested_batch_size


class AgentModelError(AgentExecutionError):
    termination_reason = "model_error"


class AgentModelResponseError(AgentExecutionError):
    termination_reason = "model_response_error"


class _AgentToolIdentityError(AgentExecutionError):
    def __init__(self, *args, tool_name: str, tool_call_id: str, call_ordinal: int, **kwargs) -> None:
        tool_name = require_ijson_text(tool_name, "tool_name", nonempty=True)
        tool_call_id = require_ijson_text(tool_call_id, "tool_call_id", nonempty=True)
        call_ordinal = require_ijson_integer(call_ordinal, "call_ordinal", minimum=1)
        super().__init__(*args, **kwargs)
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id
        self.call_ordinal = call_ordinal


class AgentUnknownToolError(_AgentToolIdentityError):
    termination_reason = "unknown_tool"


class AgentToolInputValidationError(_AgentToolIdentityError):
    termination_reason = "tool_input_validation_error"


class AgentToolError(_AgentToolIdentityError):
    termination_reason = "tool_error"


class AgentToolOutputValidationError(_AgentToolIdentityError):
    termination_reason = "tool_output_validation_error"


class AgentOutputValidationError(AgentExecutionError):
    termination_reason = "output_validation_error"
