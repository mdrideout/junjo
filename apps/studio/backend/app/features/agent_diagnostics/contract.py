"""Strict telemetry-contract parsing helpers for Agent diagnostics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import rfc8785

from app.features.agent_diagnostics.schemas import (
    AgentUsage,
    CancellationEvidence,
    CandidateEvidence,
    ExecutionError,
    ModelUsage,
    UsageAggregate,
)
from app.features.store_diagnostics.payloads import (
    DuplicateJsonObjectNameError,
    NonPortableJsonValueError,
    PayloadNestingDepthError,
    decode_json_value,
    parse_payload_slot,
)
from app.features.store_diagnostics.schemas import EvidenceDiagnostic, PayloadEvidence
from app.features.telemetry_contract.scalars import (
    ACTIVE_TELEMETRY_CONTRACT_VERSION,
    is_active_contract_version,
    is_contract_int,
    is_portable_text,
    portable_diagnostic_text,
    span_evidence_path,
)


@dataclass(frozen=True)
class AgentDefinitionContext:
    """Validated definition facts used to check normalized requests."""

    agent_key: str
    instructions: str
    tools: list[dict[str, Any]]
    tool_structural_ids: dict[str, str]
    output_schema: dict[str, Any]


class AgentEvidenceError(Exception):
    """A semantic Agent query cannot return a typed result."""

    def __init__(
        self,
        code: Literal["unsupported_contract", "unidentifiable_agent"],
        message: str,
        diagnostics: list[EvidenceDiagnostic] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.diagnostics = diagnostics or []


def diagnostic(code: str, path: str, message: str) -> EvidenceDiagnostic:
    return EvidenceDiagnostic(
        code=portable_diagnostic_text(code, fallback="invalid_evidence"),
        path=portable_diagnostic_text(path, fallback="evidence"),
        message=portable_diagnostic_text(
            message,
            fallback="Evidence contains nonportable diagnostic text.",
        ),
    )


def payload_slot_present(attributes: dict[str, Any], root: str) -> bool:
    """Return whether any content, mode, policy, or reference member exists."""
    return any(
        key in attributes for key in (root, f"{root}.mode", f"{root}.policy", f"{root}.reference")
    )


def candidate_present(attributes: dict[str, Any], root: str) -> bool:
    """Return whether any candidate availability, reason, or payload member exists."""
    return payload_slot_present(attributes, root) or any(
        key in attributes for key in (f"{root}.available", f"{root}.unavailable_reason")
    )


def forbid_payload_slot(
    attributes: dict[str, Any],
    root: str,
    diagnostics: list[EvidenceDiagnostic],
    *,
    code: str,
    message: str,
) -> bool:
    """Diagnose a conditionally forbidden payload and report whether it existed."""
    present = payload_slot_present(attributes, root)
    if present:
        diagnostics.append(diagnostic(code, root, message))
    return present


def required_int(
    attributes: dict[str, Any],
    key: str,
    diagnostics: list[EvidenceDiagnostic],
    *,
    minimum: int = 0,
) -> int | None:
    value = attributes.get(key)
    if not is_contract_int(value, minimum=minimum):
        diagnostics.append(diagnostic("invalid_contract_integer", key, f"{key} is invalid."))
        return None
    return value


def required_string(
    attributes: dict[str, Any], key: str, diagnostics: list[EvidenceDiagnostic]
) -> str | None:
    value = attributes.get(key)
    if not isinstance(value, str) or not value:
        diagnostics.append(diagnostic("required_identity_missing", key, f"{key} is absent."))
        return None
    if not is_portable_text(value, nonempty=True):
        diagnostics.append(
            diagnostic(
                "nonportable_scalar_text",
                key,
                f"{key} is not interoperable Unicode text.",
            )
        )
        return None
    return value


def parse_json_attribute(
    attributes: dict[str, Any], key: str, diagnostics: list[EvidenceDiagnostic]
) -> Any | None:
    raw = attributes.get(key)
    if not isinstance(raw, str):
        diagnostics.append(diagnostic("required_json_missing", key, f"{key} is absent."))
        return None
    try:
        return decode_json_value(raw)
    except DuplicateJsonObjectNameError:
        diagnostics.append(
            diagnostic(
                "duplicate_json_object_name",
                key,
                f"{key} repeats a JSON object name.",
            )
        )
        return None
    except NonPortableJsonValueError:
        diagnostics.append(
            diagnostic(
                "nonportable_json_value",
                key,
                f"{key} is outside the I-JSON interoperability domain.",
            )
        )
        return None
    except PayloadNestingDepthError:
        diagnostics.append(
            diagnostic(
                "payload_nesting_too_deep",
                key,
                f"{key} exceeds the contract payload nesting bound.",
            )
        )
        return None
    except (json.JSONDecodeError, ValueError):
        diagnostics.append(diagnostic("invalid_json", key, f"{key} is not valid finite JSON."))
        return None


def require_active_contract(
    attributes: dict[str, Any], *, owner: bool, diagnostics: list[EvidenceDiagnostic]
) -> bool:
    version = attributes.get("junjo.telemetry.contract_version")
    if is_active_contract_version(version):
        return True
    issue = diagnostic(
        "unsupported_contract",
        "junjo.telemetry.contract_version",
        (f"Expected telemetry contract {ACTIVE_TELEMETRY_CONTRACT_VERSION}; observed {version!r}."),
    )
    if owner:
        raise AgentEvidenceError("unsupported_contract", issue.message, [issue])
    diagnostics.append(issue)
    return False


def parse_candidate(
    attributes: dict[str, Any], root: str, diagnostics: list[EvidenceDiagnostic]
) -> CandidateEvidence:
    allowed_reasons = {
        "junjo.agent.input_candidate": {"not_json_serializable"},
        "junjo.agent.history_candidate": {"not_json_serializable"},
        "junjo.agent.model.response_candidate": {
            "not_returned",
            "cancelled",
            "not_json_serializable",
        },
        "junjo.agent.tool.result_candidate": {
            "not_invoked",
            "service_failed",
            "cancelled",
            "not_json_serializable",
        },
    }.get(root, set())
    available = attributes.get(f"{root}.available")
    if available is True:
        if f"{root}.unavailable_reason" in attributes:
            diagnostics.append(
                diagnostic(
                    "invalid_candidate_evidence",
                    f"{root}.unavailable_reason",
                    "Available candidate cannot carry an unavailable reason.",
                )
            )
        payload, issues = parse_payload_slot(attributes, root, required=True)
        diagnostics.extend(issues)
        assert payload is not None
        return CandidateEvidence(available=True, payload=payload, unavailable_reason=None)
    if available is False:
        forbid_payload_slot(
            attributes,
            root,
            diagnostics,
            code="invalid_candidate_evidence",
            message="Unavailable candidate cannot carry payload evidence.",
        )
        reason = attributes.get(f"{root}.unavailable_reason")
        if not isinstance(reason, str) or reason not in allowed_reasons:
            diagnostics.append(
                diagnostic(
                    "invalid_candidate_evidence",
                    f"{root}.unavailable_reason",
                    "Unavailable candidate reason is invalid.",
                )
            )
            reason = "contract_evidence_missing"
        return CandidateEvidence(available=False, payload=None, unavailable_reason=reason)

    diagnostics.append(
        diagnostic(
            "invalid_candidate_evidence",
            f"{root}.available",
            "Candidate availability is absent or invalid.",
        )
    )
    return CandidateEvidence(
        available=False,
        payload=None,
        unavailable_reason="contract_evidence_missing",
    )


def parse_agent_usage(
    attributes: dict[str, Any], diagnostics: list[EvidenceDiagnostic]
) -> AgentUsage | None:
    root = "junjo.agent.usage"
    value = parse_json_attribute(attributes, root, diagnostics)
    if not isinstance(value, dict) or value.get("v") != 1 or type(value.get("v")) is not int:
        diagnostics.append(diagnostic("invalid_usage", root, "Agent usage shape is invalid."))
        return None
    responses = value.get("modelResponses")
    fields = value.get("fields")
    if not is_contract_int(responses) or not isinstance(fields, dict):
        diagnostics.append(diagnostic("invalid_usage", root, "Agent usage counts are invalid."))
        return None
    allowed = {
        "inputTokens",
        "outputTokens",
        "cachedInputTokens",
        "reasoningTokens",
        "totalTokens",
    }
    parsed_fields: dict[str, UsageAggregate] = {}
    if set(fields) - allowed:
        diagnostics.append(diagnostic("invalid_usage", root, "Agent usage field is unsupported."))
        return None
    for key, aggregate in fields.items():
        if not isinstance(aggregate, dict):
            diagnostics.append(diagnostic("invalid_usage", root, "Usage aggregate is invalid."))
            return None
        total = aggregate.get("sum")
        observations = aggregate.get("observations")
        if not is_contract_int(total) or not is_contract_int(observations, minimum=1):
            diagnostics.append(
                diagnostic("invalid_usage", root, "Usage aggregate counts are invalid.")
            )
            return None
        parsed_fields[key] = UsageAggregate(sum=total, observations=observations)
    return AgentUsage(model_responses=responses, fields=parsed_fields)


def parse_model_usage(
    attributes: dict[str, Any], diagnostics: list[EvidenceDiagnostic]
) -> ModelUsage | None:
    root = "junjo.agent.model.usage"
    if root not in attributes:
        return None
    value = parse_json_attribute(attributes, root, diagnostics)
    allowed = {
        "v",
        "inputTokens",
        "outputTokens",
        "cachedInputTokens",
        "reasoningTokens",
        "totalTokens",
    }
    if (
        not isinstance(value, dict)
        or value.get("v") != 1
        or type(value.get("v")) is not int
        or set(value) - allowed
    ):
        diagnostics.append(diagnostic("invalid_usage", root, "Model usage shape is invalid."))
        return None
    for key, item in value.items():
        if key != "v" and not is_contract_int(item):
            diagnostics.append(diagnostic("invalid_usage", root, "Model usage count is invalid."))
            return None
    return ModelUsage(
        input_tokens=value.get("inputTokens"),
        output_tokens=value.get("outputTokens"),
        cached_input_tokens=value.get("cachedInputTokens"),
        reasoning_tokens=value.get("reasoningTokens"),
        total_tokens=value.get("totalTokens"),
    )


def parse_time(value: Any, path: str) -> datetime:
    if not isinstance(value, str):
        raise AgentEvidenceError(
            "unidentifiable_agent",
            f"Agent timestamp {path} is absent.",
            [diagnostic("required_identity_missing", path, "Timestamp is absent.")],
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise AgentEvidenceError(
            "unidentifiable_agent",
            f"Agent timestamp {path} is invalid.",
            [diagnostic("required_identity_missing", path, "Timestamp is invalid.")],
        ) from error
    if parsed.tzinfo is None:
        raise AgentEvidenceError(
            "unidentifiable_agent",
            f"Agent timestamp {path} lacks an offset.",
            [diagnostic("required_identity_missing", path, "Timestamp lacks an offset.")],
        )
    return parsed


def duration_ns(span: dict[str, Any], start: datetime, end: datetime) -> int:
    if end < start:
        raise AgentEvidenceError(
            "unidentifiable_agent",
            "Span interval ends before it starts.",
            [
                diagnostic(
                    "invalid_span_interval",
                    "span.interval",
                    "Span end time cannot precede start time.",
                )
            ],
        )
    stored = span.get("duration_ns")
    if is_contract_int(stored):
        return stored
    derived = int((end - start).total_seconds() * 1_000_000_000)
    if not is_contract_int(derived):
        raise AgentEvidenceError(
            "unidentifiable_agent",
            "Agent duration is outside the portable integer domain.",
            [
                diagnostic(
                    "invalid_contract_integer",
                    "duration_ns",
                    "Duration cannot be represented safely in the semantic API.",
                )
            ],
        )
    return derived


def operation_outcome(
    span: dict[str, Any], attributes: dict[str, Any]
) -> Literal["completed", "failed", "cancelled"]:
    if attributes.get("junjo.cancelled") is True:
        return "cancelled"
    if span.get("status_code") == "2" or "error.type" in attributes:
        return "failed"
    return "completed"


def _optional_portable_text(
    value: Any,
    path: str,
    diagnostics: list[EvidenceDiagnostic],
) -> str | None:
    if value is None:
        return None
    if not is_portable_text(value):
        diagnostics.append(
            diagnostic(
                "nonportable_scalar_text",
                path,
                f"{path} is not interoperable Unicode text.",
            )
        )
        return None
    return value


def execution_error(
    span: dict[str, Any],
    attributes: dict[str, Any],
    diagnostics: list[EvidenceDiagnostic],
) -> ExecutionError | None:
    error_type = attributes.get("error.type")
    if not is_portable_text(error_type, nonempty=True):
        return None
    message = _optional_portable_text(
        span.get("status_message") or None,
        "status_message",
        diagnostics,
    )
    stacktrace: str | None = None
    raw_events = span.get("events_json")
    events = raw_events if isinstance(raw_events, list) else []
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict) or event.get("name") != "exception":
                continue
            event_attributes = event.get("attributes")
            if isinstance(event_attributes, dict):
                raw_message = event_attributes.get("exception.message")
                raw_stack = event_attributes.get("exception.stacktrace")
                if raw_message is not None:
                    message = _optional_portable_text(
                        raw_message,
                        "exception.message",
                        diagnostics,
                    )
                if raw_stack is not None:
                    stacktrace = _optional_portable_text(
                        raw_stack,
                        "exception.stacktrace",
                        diagnostics,
                    )
                break
    return ExecutionError(type=error_type, message=message, stacktrace=stacktrace)


def exception_type_matches(error_type: Any, exception_types: set[Any]) -> bool:
    """Match OTel's qualified exception type to the semantic error classification."""
    if not is_portable_text(error_type, nonempty=True):
        return False
    return any(
        exception_type == error_type
        or (
            is_portable_text(exception_type, nonempty=True)
            and exception_type.rsplit(".", 1)[-1] == error_type
        )
        for exception_type in exception_types
    )


def cancellation_evidence(
    attributes: dict[str, Any],
    diagnostics: list[EvidenceDiagnostic],
) -> CancellationEvidence | None:
    if attributes.get("junjo.cancelled") is not True:
        return None
    reason = attributes.get("junjo.cancelled_reason")
    return CancellationEvidence(
        reason=_optional_portable_text(
            reason,
            "junjo.cancelled_reason",
            diagnostics,
        )
    )


def validate_operation_transport(
    span: dict[str, Any],
    attributes: dict[str, Any],
    diagnostics: list[EvidenceDiagnostic],
) -> None:
    outcome = operation_outcome(span, attributes)
    status_is_error = span.get("status_code") == "2"
    error_type = attributes.get("error.type")
    span_path = span_evidence_path(span)
    event_path = span_evidence_path(span, "events_json")
    raw_events = span.get("events_json")
    if raw_events is None:
        diagnostics.append(
            diagnostic(
                "missing_operation_event_evidence",
                event_path,
                "Operation event evidence is absent.",
            )
        )
        events: list[dict[str, Any]] = []
    elif not isinstance(raw_events, list):
        diagnostics.append(
            diagnostic(
                "invalid_operation_event_evidence",
                event_path,
                "Operation event evidence must be a list.",
            )
        )
        events = []
    else:
        events = []
        for index, event in enumerate(raw_events):
            if not isinstance(event, dict):
                diagnostics.append(
                    diagnostic(
                        "invalid_operation_event_evidence",
                        f"{event_path}[{index}]",
                        "Operation event evidence must contain objects.",
                    )
                )
                continue
            events.append(event)
    exception_types = {
        event_attributes.get("exception.type")
        for event in events
        for event_attributes in [event.get("attributes") if isinstance(event, dict) else None]
        if isinstance(event, dict)
        and event.get("name") == "exception"
        and isinstance(event_attributes, dict)
        and is_portable_text(event_attributes.get("exception.type"), nonempty=True)
    }
    if outcome == "failed" and (
        not status_is_error
        or not exception_type_matches(error_type, exception_types)
        or attributes.get("junjo.cancelled") is True
    ):
        diagnostics.append(
            diagnostic(
                "invalid_operation_failure_evidence",
                span_path,
                "Failed operation requires matching error status, type, and exception evidence.",
            )
        )
    elif outcome == "cancelled":
        reason = attributes.get("junjo.cancelled_reason")
        if (
            not is_portable_text(reason, nonempty=True)
            or status_is_error
            or "error.type" in attributes
        ):
            diagnostics.append(
                diagnostic(
                    "invalid_operation_cancellation_evidence",
                    span_path,
                    "Cancelled operation requires a reason and non-error transport evidence.",
                )
            )
    elif outcome == "completed" and (
        status_is_error or "error.type" in attributes or attributes.get("junjo.cancelled") is True
    ):
        diagnostics.append(
            diagnostic(
                "invalid_operation_completion_evidence",
                span_path,
                "Completed operation cannot carry failure or cancellation evidence.",
            )
        )


def _is_nonempty_string(value: Any) -> bool:
    return is_portable_text(value, nonempty=True)


def _exact_keys(value: Any, required: set[str], optional: set[str] | None = None) -> bool:
    optional = optional or set()
    return isinstance(value, dict) and set(value) >= required and set(value) <= required | optional


def _valid_tool_descriptor(value: Any, *, structural: bool) -> bool:
    required = {"name", "description", "inputSchema", "outputSchema"}
    if structural:
        required.add("structuralId")
    if not _exact_keys(value, required):
        return False
    if not _is_nonempty_string(value["name"]) or not isinstance(value["description"], str):
        return False
    if not isinstance(value["inputSchema"], dict) or not isinstance(value["outputSchema"], dict):
        return False
    if structural and (
        not isinstance(value["structuralId"], str)
        or not value["structuralId"].startswith("tool_sha256:")
        or len(value["structuralId"]) != 76
    ):
        return False
    return True


def _structural_digest(prefix: str, material: dict[str, Any]) -> str:
    return f"{prefix}_sha256:{hashlib.sha256(rfc8785.dumps(material)).hexdigest()}"


def _safe_structural_digest(
    prefix: str,
    material: dict[str, Any],
    path: str,
    diagnostics: list[EvidenceDiagnostic],
) -> str | None:
    try:
        return _structural_digest(prefix, material)
    except rfc8785.CanonicalizationError as error:
        diagnostics.append(
            diagnostic(
                "invalid_structural_material",
                path,
                f"Structural material is outside the RFC 8785 I-JSON domain: {error}",
            )
        )
        return None


def validate_definition_snapshot(
    payload: PayloadEvidence,
    owner_attributes: dict[str, Any],
    diagnostics: list[EvidenceDiagnostic],
) -> AgentDefinitionContext | None:
    """Validate full definition shape, fingerprints, and owner correspondence."""
    if payload.mode != "full":
        return None
    value = payload.value
    required = {
        "v",
        "agentKey",
        "name",
        "instructions",
        "inputSchema",
        "model",
        "tools",
        "outputSchema",
        "limits",
        "structuralId",
    }
    if not _exact_keys(value, required):
        diagnostics.append(
            diagnostic(
                "invalid_definition_snapshot",
                "junjo.agent.definition_snapshot",
                "Definition shape is invalid.",
            )
        )
        return None
    model = value["model"]
    limits = value["limits"]
    tools = value["tools"]
    valid = (
        value["v"] == 1
        and type(value["v"]) is int
        and _is_nonempty_string(value["agentKey"])
        and _is_nonempty_string(value["name"])
        and isinstance(value["instructions"], str)
        and isinstance(value["inputSchema"], dict)
        and isinstance(value["outputSchema"], dict)
        and _exact_keys(model, {"driverKey", "provider", "model", "settings"})
        and _is_nonempty_string(model.get("driverKey"))
        and _is_nonempty_string(model.get("provider"))
        and _is_nonempty_string(model.get("model"))
        and isinstance(model.get("settings"), dict)
        and isinstance(tools, list)
        and all(_valid_tool_descriptor(tool, structural=True) for tool in tools)
        and _exact_keys(limits, {"modelRequests", "toolCalls"})
        and is_contract_int(limits.get("modelRequests"), minimum=1)
        and is_contract_int(limits.get("toolCalls"), minimum=1)
        and isinstance(value["structuralId"], str)
    )
    if not valid:
        diagnostics.append(
            diagnostic(
                "invalid_definition_snapshot",
                "junjo.agent.definition_snapshot",
                "Definition values are invalid.",
            )
        )
        return None

    tool_names = [tool["name"] for tool in tools]
    if len(tool_names) != len(set(tool_names)):
        diagnostics.append(
            diagnostic(
                "duplicate_tool_definition",
                "junjo.agent.definition_snapshot.tools",
                "Tool definition names must be unique.",
            )
        )

    for index, tool in enumerate(tools):
        material = {
            "v": 1,
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["inputSchema"],
            "outputSchema": tool["outputSchema"],
        }
        expected_tool_id = _safe_structural_digest(
            "tool",
            material,
            f"junjo.agent.definition_snapshot.tools[{index}]",
            diagnostics,
        )
        if expected_tool_id is not None and tool["structuralId"] != expected_tool_id:
            diagnostics.append(
                diagnostic(
                    "structural_identity_mismatch",
                    f"junjo.agent.definition_snapshot.tools[{index}].structuralId",
                    "Tool structural fingerprint does not match its material.",
                )
            )

    structural_tools = [
        {
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["inputSchema"],
            "outputSchema": tool["outputSchema"],
        }
        for tool in tools
    ]
    material = {
        "v": 1,
        "agentKey": value["agentKey"],
        "instructions": value["instructions"],
        "inputSchema": value["inputSchema"],
        "model": model,
        "tools": structural_tools,
        "outputSchema": value["outputSchema"],
        "limits": limits,
    }
    expected_structural_id = _safe_structural_digest(
        "agent",
        material,
        "junjo.agent.definition_snapshot",
        diagnostics,
    )
    correspondence = {
        "agentKey": owner_attributes.get("junjo.agent.key"),
        "name": owner_attributes.get("junjo.agent.name"),
        "structuralId": owner_attributes.get("junjo.executable_structural_id"),
    }
    for key, owner_value in correspondence.items():
        if value[key] != owner_value:
            diagnostics.append(
                diagnostic(
                    "definition_owner_mismatch",
                    f"junjo.agent.definition_snapshot.{key}",
                    "Definition fact does not match its owner.",
                )
            )
    if expected_structural_id is not None and value["structuralId"] != expected_structural_id:
        diagnostics.append(
            diagnostic(
                "structural_identity_mismatch",
                "junjo.agent.definition_snapshot.structuralId",
                "Agent structural fingerprint does not match its material.",
            )
        )
    if limits.get("modelRequests") != owner_attributes.get(
        "junjo.agent.limit.model_requests"
    ) or limits.get("toolCalls") != owner_attributes.get("junjo.agent.limit.tool_calls"):
        diagnostics.append(
            diagnostic(
                "definition_owner_mismatch",
                "junjo.agent.definition_snapshot.limits",
                "Definition limits do not match owner limits.",
            )
        )
    return AgentDefinitionContext(
        agent_key=value["agentKey"],
        instructions=value["instructions"],
        tools=structural_tools,
        tool_structural_ids={tool["name"]: tool["structuralId"] for tool in tools},
        output_schema=value["outputSchema"],
    )


def _valid_tool_call(value: Any) -> bool:
    return (
        _exact_keys(value, {"id", "name", "arguments"})
        and _is_nonempty_string(value["id"])
        and _is_nonempty_string(value["name"])
        and isinstance(value["arguments"], dict)
    )


def _valid_message(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    message_type = value.get("type")
    if message_type == "agent_input":
        return _exact_keys(value, {"type", "input"})
    if message_type == "assistant_output":
        return _exact_keys(value, {"type", "output"})
    if message_type == "assistant_tool_calls":
        return (
            _exact_keys(value, {"type", "calls"}, {"assistantText"})
            and isinstance(value["calls"], list)
            and bool(value["calls"])
            and all(_valid_tool_call(call) for call in value["calls"])
            and (
                "assistantText" not in value
                or value["assistantText"] is None
                or isinstance(value["assistantText"], str)
            )
        )
    if message_type == "tool_result":
        return (
            _exact_keys(value, {"type", "callId", "toolName", "result"})
            and _is_nonempty_string(value["callId"])
            and _is_nonempty_string(value["toolName"])
        )
    return False


def validate_model_request(
    payload: PayloadEvidence,
    operation_attributes: dict[str, Any],
    definition: AgentDefinitionContext | None,
    diagnostics: list[EvidenceDiagnostic],
) -> None:
    """Validate a normalized model request and its operation identities."""
    if payload.mode != "full":
        return
    value = payload.value
    required = {
        "v",
        "agentKey",
        "runId",
        "ordinal",
        "instructions",
        "messages",
        "tools",
        "outputSchema",
    }
    valid = (
        _exact_keys(value, required)
        and value["v"] == 1
        and type(value["v"]) is int
        and _is_nonempty_string(value["agentKey"])
        and _is_nonempty_string(value["runId"])
        and is_contract_int(value["ordinal"], minimum=1)
        and isinstance(value["instructions"], str)
        and isinstance(value["messages"], list)
        and all(_valid_message(message) for message in value["messages"])
        and isinstance(value["tools"], list)
        and all(_valid_tool_descriptor(tool, structural=False) for tool in value["tools"])
        and isinstance(value["outputSchema"], dict)
    )
    if not valid:
        diagnostics.append(
            diagnostic(
                "invalid_model_request",
                "junjo.agent.model.request",
                "Normalized request shape is invalid.",
            )
        )
        return
    if (
        value["agentKey"] != operation_attributes.get("junjo.agent.key")
        or value["runId"] != operation_attributes.get("junjo.agent.runtime_id")
        or value["ordinal"] != operation_attributes.get("junjo.agent.model_request.ordinal")
    ):
        diagnostics.append(
            diagnostic(
                "model_request_identity_mismatch",
                "junjo.agent.model.request",
                "Request identity does not match operation identity.",
            )
        )
    if definition is not None and (
        value["agentKey"] != definition.agent_key
        or value["instructions"] != definition.instructions
        or value["tools"] != definition.tools
        or value["outputSchema"] != definition.output_schema
    ):
        diagnostics.append(
            diagnostic(
                "model_request_definition_mismatch",
                "junjo.agent.model.request",
                "Request does not match the Agent definition.",
            )
        )


def validate_model_response(
    payload: PayloadEvidence,
    response_type: str,
    diagnostics: list[EvidenceDiagnostic],
) -> bool:
    """Validate inspectable normalized response content.

    A non-full payload still proves that a normalized response occurred when its
    scalar response type and payload slot are present. Its transformed content
    is intentionally outside the original response schema.
    """
    if payload.mode != "full":
        return False
    value = payload.value
    if response_type == "final_output":
        valid = (
            _exact_keys(value, {"v", "type", "output"}, {"usage"})
            and value.get("type") == "final_output"
        )
    elif response_type == "tool_calls":
        valid = (
            _exact_keys(value, {"v", "type", "calls"}, {"assistantText", "usage"})
            and value.get("type") == "tool_calls"
            and isinstance(value.get("calls"), list)
            and bool(value["calls"])
            and all(_valid_tool_call(call) for call in value["calls"])
            and len({call["id"] for call in value["calls"]}) == len(value["calls"])
            and (
                "assistantText" not in value
                or value["assistantText"] is None
                or isinstance(value["assistantText"], str)
            )
        )
    else:
        valid = False
    if valid:
        valid = value.get("v") == 1 and type(value.get("v")) is int
    if valid and "usage" in value:
        usage = value["usage"]
        valid = (
            isinstance(usage, dict)
            and usage.get("v") == 1
            and type(usage.get("v")) is int
            and set(usage)
            <= {
                "v",
                "inputTokens",
                "outputTokens",
                "cachedInputTokens",
                "reasoningTokens",
                "totalTokens",
            }
            and all(key == "v" or is_contract_int(item) for key, item in usage.items())
        )
    if not valid:
        diagnostics.append(
            diagnostic(
                "invalid_model_response",
                "junjo.agent.model.response",
                "Normalized response shape is invalid.",
            )
        )
    return valid
