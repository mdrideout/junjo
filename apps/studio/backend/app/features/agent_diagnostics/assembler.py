"""Assemble typed Agent execution diagnostics from preserved OTLP spans."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.features.agent_diagnostics.contract import (
    AgentDefinitionContext,
    AgentEvidenceError,
    cancellation_evidence,
    candidate_present,
    diagnostic,
    duration_ns,
    exception_type_matches,
    execution_error,
    is_contract_int,
    is_portable_text,
    operation_outcome,
    parse_agent_usage,
    parse_candidate,
    parse_model_usage,
    parse_time,
    payload_slot_present,
    require_active_contract,
    required_int,
    required_string,
    validate_definition_snapshot,
    validate_model_request,
    validate_model_response,
    validate_operation_transport,
)
from app.features.agent_diagnostics.schemas import (
    AgentCounts,
    AgentExecutionDetail,
    AgentExecutionSummary,
    AgentLimits,
    AgentOperation,
    ModelOperation,
    NestedExecutableReference,
    ParentExecutableReference,
    RequestedToolCall,
    ServiceIdentity,
    ToolCallCounts,
    ToolOperation,
)
from app.features.store_diagnostics.integrity import assemble_evidence_integrity
from app.features.store_diagnostics.payloads import parse_payload_slot
from app.features.store_diagnostics.reconstruction import (
    AGENT_STORE_BOUNDARY,
    reconstruct_store,
)
from app.features.store_diagnostics.schemas import EvidenceDiagnostic
from app.features.telemetry_contract.scalars import (
    is_lower_hex,
    is_portable_enum,
    span_evidence_path,
)


def _attributes(span: dict[str, Any]) -> dict[str, Any]:
    value = span.get("attributes_json")
    return value if isinstance(value, dict) else {}


def _resource(span: dict[str, Any]) -> dict[str, Any]:
    value = span.get("resource_attributes_json")
    return value if isinstance(value, dict) else {}


def _service_identity(span: dict[str, Any]) -> ServiceIdentity:
    resource = _resource(span)
    name = resource.get("service.name")
    namespace = resource.get("service.namespace", "")
    version = resource.get("service.version")
    if not is_portable_text(name, nonempty=True):
        code = (
            "nonportable_scalar_text"
            if isinstance(name, str) and name
            else "required_identity_missing"
        )
        raise AgentEvidenceError(
            "unidentifiable_agent",
            "Agent resource service.name is absent or invalid.",
            [diagnostic(code, "resource.service.name", "Service name is absent or invalid.")],
        )
    if not is_portable_text(namespace):
        raise AgentEvidenceError(
            "unidentifiable_agent",
            "Agent resource service.namespace is invalid.",
            [
                diagnostic(
                    "nonportable_scalar_text"
                    if isinstance(namespace, str)
                    else "required_identity_missing",
                    "resource.service.namespace",
                    "Service namespace is invalid.",
                )
            ],
        )
    if version is not None and not is_portable_text(version, nonempty=True):
        raise AgentEvidenceError(
            "unidentifiable_agent",
            "Agent resource service.version is invalid.",
            [
                diagnostic(
                    "nonportable_scalar_text"
                    if isinstance(version, str) and version
                    else "required_identity_missing",
                    "resource.service.version",
                    "Service version is invalid.",
                )
            ],
        )
    return ServiceIdentity(namespace=namespace, name=name, version=version)


def _required_summary_value[T](value: T | None, path: str) -> T:
    if value is None:
        raise AgentEvidenceError(
            "unidentifiable_agent",
            f"Agent summary field {path} is invalid.",
            [diagnostic("unidentifiable_agent", path, "Required summary field is invalid.")],
        )
    return value


def _validate_owner_terminal_transport(
    owner_span: dict[str, Any],
    attributes: dict[str, Any],
    diagnostics: list[EvidenceDiagnostic],
) -> None:
    outcome = attributes.get("junjo.agent.outcome")
    status_is_error = owner_span.get("status_code") == "2"
    error_type = attributes.get("error.type")
    raw_events = owner_span.get("events_json")
    events = raw_events if isinstance(raw_events, list) else []
    exception_types = {
        event_attributes.get("exception.type")
        for event in events
        for event_attributes in [event.get("attributes") if isinstance(event, dict) else None]
        if isinstance(event, dict)
        and event.get("name") == "exception"
        and isinstance(event_attributes, dict)
        and is_portable_text(event_attributes.get("exception.type"), nonempty=True)
    }
    if outcome == "failed":
        if not status_is_error or not exception_type_matches(error_type, exception_types):
            diagnostics.append(
                diagnostic(
                    "invalid_failure_evidence",
                    "owner.status",
                    "Failed Agent requires matching error status, type, and exception evidence.",
                )
            )
        if attributes.get("junjo.cancelled") is True:
            diagnostics.append(
                diagnostic(
                    "invalid_failure_evidence",
                    "junjo.cancelled",
                    "Failed Agent cannot also be execution-cancelled.",
                )
            )
    elif outcome == "cancelled":
        reason = attributes.get("junjo.cancelled_reason")
        if (
            attributes.get("junjo.cancelled") is not True
            or not is_portable_text(reason, nonempty=True)
            or status_is_error
            or "error.type" in attributes
        ):
            diagnostics.append(
                diagnostic(
                    "invalid_cancellation_evidence",
                    "junjo.cancelled",
                    "Cancelled Agent requires a reason and non-error transport ownership.",
                )
            )
    elif outcome == "completed" and (
        status_is_error or "error.type" in attributes or attributes.get("junjo.cancelled") is True
    ):
        diagnostics.append(
            diagnostic(
                "invalid_completion_evidence",
                "owner.status",
                "Completed Agent cannot carry execution failure or cancellation evidence.",
            )
        )


def _validate_limit_evidence(
    attributes: dict[str, Any],
    diagnostics: list[EvidenceDiagnostic],
) -> None:
    roots = {
        "junjo.agent.limit.exceeded",
        "junjo.agent.limit.attempted_count",
        "junjo.agent.limit.requested_batch_size",
    }
    if attributes.get("junjo.agent.termination_reason") != "limit_exceeded":
        if roots & set(attributes):
            diagnostics.append(
                diagnostic(
                    "unexpected_limit_evidence",
                    "junjo.agent.limit",
                    "Limit-exceeded evidence exists on a different terminal reason.",
                )
            )
        return

    exceeded = attributes.get("junjo.agent.limit.exceeded")
    attempted = attributes.get("junjo.agent.limit.attempted_count")
    if not is_portable_enum(exceeded, {"model_requests", "tool_calls"}) or not is_contract_int(
        attempted, minimum=1
    ):
        diagnostics.append(
            diagnostic(
                "invalid_limit_evidence",
                "junjo.agent.limit",
                "Limit-exceeded kind or attempted count is invalid.",
            )
        )
        return
    if exceeded == "model_requests":
        count = attributes.get("junjo.agent.model_request.count")
        limit = attributes.get("junjo.agent.limit.model_requests")
        if (
            count != limit
            or attempted != count + 1
            or "junjo.agent.limit.requested_batch_size" in attributes
        ):
            diagnostics.append(
                diagnostic(
                    "invalid_limit_evidence",
                    "junjo.agent.limit",
                    "Model-request limit evidence does not reconcile.",
                )
            )
        return
    batch_size = attributes.get("junjo.agent.limit.requested_batch_size")
    requested = attributes.get("junjo.agent.tool_call.requested_count")
    admitted = attributes.get("junjo.agent.tool_call.admitted_count")
    limit = attributes.get("junjo.agent.limit.tool_calls")
    if (
        not is_contract_int(batch_size, minimum=1)
        or not is_contract_int(requested)
        or not is_contract_int(admitted)
        or not is_contract_int(limit, minimum=1)
        or requested <= limit
        or attempted != admitted + batch_size
    ):
        diagnostics.append(
            diagnostic(
                "invalid_limit_evidence",
                "junjo.agent.limit",
                "Tool-call limit evidence does not reconcile.",
            )
        )


def _validate_owner_conditional_evidence(
    attributes: dict[str, Any],
    usage: Any,
    diagnostics: list[EvidenceDiagnostic],
) -> None:
    """Validate owner-only iff rules before emitting a summary without integrity."""
    state_available = attributes.get("junjo.agent.state.available")
    termination = attributes.get("junjo.agent.termination_reason")
    outcome = attributes.get("junjo.agent.outcome")
    expected_outcome = (
        "completed"
        if termination == "final_output"
        else "cancelled"
        if termination == "cancelled"
        else "failed"
    )
    if outcome != expected_outcome:
        diagnostics.append(
            diagnostic(
                "terminal_outcome_reason_mismatch",
                "junjo.agent.termination_reason",
                "Agent outcome does not match its termination reason.",
            )
        )
    if not isinstance(state_available, bool):
        diagnostics.append(
            diagnostic(
                "invalid_state_availability",
                "junjo.agent.state.available",
                "Agent state availability is absent or invalid.",
            )
        )
    elif not state_available:
        allowed_unavailable = termination in {
            "input_validation_error",
            "history_validation_error",
        } or (
            termination == "internal_error"
            and attributes.get("error.type") == "AgentAdmissionError"
        )
        if not allowed_unavailable:
            diagnostics.append(
                diagnostic(
                    "invalid_unavailable_agent_state",
                    "junjo.agent.state.available",
                    "State may be unavailable only before Agent admission.",
                )
            )
        count_keys = (
            "junjo.agent.operation.count",
            "junjo.agent.model_request.count",
            "junjo.agent.tool_call.requested_count",
            "junjo.agent.tool_call.admitted_count",
            "junjo.agent.tool_call.started_count",
            "junjo.agent.tool_call.completed_count",
        )
        empty_usage = usage is not None and usage.model_responses == 0 and not usage.fields
        if any(attributes.get(key) != 0 for key in count_keys) or not empty_usage:
            diagnostics.append(
                diagnostic(
                    "invalid_unavailable_agent_activity",
                    "junjo.agent.state.available",
                    "State-unavailable Agent cannot carry operation, count, or usage activity.",
                )
            )
    requires_unavailable_state = termination in {
        "input_validation_error",
        "history_validation_error",
    } or (
        termination == "internal_error"
        and attributes.get("error.type") == "AgentAdmissionError"
    )
    if requires_unavailable_state and state_available is not False:
        diagnostics.append(
            diagnostic(
                "invalid_unavailable_agent_state",
                "junjo.agent.state.available",
                "Boundary rejection and admission failure require unavailable state.",
            )
        )
    requested = attributes.get("junjo.agent.tool_call.requested_count")
    tool_limit = attributes.get("junjo.agent.limit.tool_calls")
    if (
        is_contract_int(requested)
        and is_contract_int(tool_limit, minimum=1)
        and requested > tool_limit
        and not (
            termination == "limit_exceeded"
            and attributes.get("junjo.agent.limit.exceeded") == "tool_calls"
        )
    ):
        diagnostics.append(
            diagnostic(
                "invalid_limit_evidence",
                "junjo.agent.limit",
                "Requested Tool count above the limit requires Tool-limit termination evidence.",
            )
        )



def assemble_agent_summary(owner_span: dict[str, Any]) -> AgentExecutionSummary:
    """Build one owner-only summary; no descendant inference is required."""
    attributes = _attributes(owner_span)
    if attributes.get("junjo.span_type") != "agent":
        issue = diagnostic(
            "invalid_agent_owner_type",
            "junjo.span_type",
            "The selected span is not an Agent.",
        )
        raise AgentEvidenceError("unidentifiable_agent", issue.message, [issue])
    diagnostics: list[EvidenceDiagnostic] = []
    require_active_contract(attributes, owner=True, diagnostics=diagnostics)

    trace_id = owner_span.get("trace_id")
    span_id = owner_span.get("span_id")
    if not is_lower_hex(trace_id, length=32):
        diagnostics.append(
            diagnostic(
                "invalid_trace_id",
                "trace_id",
                "Agent trace identity must be exact lowercase hexadecimal text.",
            )
        )
    if not is_lower_hex(span_id, length=16):
        diagnostics.append(
            diagnostic(
                "invalid_span_id",
                "span_id",
                "Agent span identity must be exact lowercase hexadecimal text.",
            )
        )
    if diagnostics:
        raise AgentEvidenceError(
            "unidentifiable_agent",
            "Agent trace/span identity is absent or invalid.",
            diagnostics,
        )
    agent_key = required_string(attributes, "junjo.agent.key", diagnostics)
    agent_name = required_string(attributes, "junjo.agent.name", diagnostics)
    structural_id = required_string(attributes, "junjo.executable_structural_id", diagnostics)
    if structural_id is not None and (
        not structural_id.startswith("agent_sha256:")
        or not is_lower_hex(structural_id.removeprefix("agent_sha256:"), length=64)
    ):
        diagnostics.append(
            diagnostic(
                "invalid_agent_structural_id",
                "junjo.executable_structural_id",
                "Agent structural identity is invalid.",
            )
        )
    definition_id = required_string(attributes, "junjo.executable_definition_id", diagnostics)
    runtime_id = required_string(attributes, "junjo.executable_runtime_id", diagnostics)
    if runtime_id != attributes.get("junjo.agent.runtime_id"):
        diagnostics.append(
            diagnostic(
                "runtime_identity_mismatch",
                "junjo.agent.runtime_id",
                "Agent runtime IDs do not match.",
            )
        )

    model_limit = required_int(
        attributes, "junjo.agent.limit.model_requests", diagnostics, minimum=1
    )
    tool_limit = required_int(attributes, "junjo.agent.limit.tool_calls", diagnostics, minimum=1)
    operation_count = required_int(attributes, "junjo.agent.operation.count", diagnostics)
    model_count = required_int(attributes, "junjo.agent.model_request.count", diagnostics)
    requested = required_int(attributes, "junjo.agent.tool_call.requested_count", diagnostics)
    admitted = required_int(attributes, "junjo.agent.tool_call.admitted_count", diagnostics)
    started = required_int(attributes, "junjo.agent.tool_call.started_count", diagnostics)
    completed = required_int(attributes, "junjo.agent.tool_call.completed_count", diagnostics)
    usage = parse_agent_usage(attributes, diagnostics)
    if all(value is not None for value in (requested, admitted, started, completed)) and not (
        completed <= started <= admitted <= requested
    ):
        diagnostics.append(
            diagnostic(
                "tool_count_inequality", "counts.tool_calls", "Tool counts are inconsistent."
            )
        )
    if admitted is not None and tool_limit is not None and admitted > tool_limit:
        diagnostics.append(
            diagnostic(
                "tool_limit_mismatch", "counts.tool_calls", "Admitted Tool count exceeds limit."
            )
        )

    outcome = attributes.get("junjo.agent.outcome")
    termination = attributes.get("junjo.agent.termination_reason")
    if not is_portable_enum(outcome, {"completed", "failed", "cancelled"}) or not is_portable_text(
        termination, nonempty=True
    ):
        raise AgentEvidenceError(
            "unidentifiable_agent",
            "Agent terminal identity is invalid.",
            diagnostics
            + [diagnostic("invalid_terminal_fact", "junjo.agent.outcome", "Outcome is invalid.")],
        )
    _validate_owner_terminal_transport(owner_span, attributes, diagnostics)
    _validate_limit_evidence(attributes, diagnostics)
    _validate_owner_conditional_evidence(attributes, usage, diagnostics)

    # A list result has no integrity envelope. Do not discard questionable owner
    # semantics there; malformed owner facts are rejected explicitly.
    if diagnostics:
        raise AgentEvidenceError(
            "unidentifiable_agent",
            "Agent owner evidence cannot produce a trustworthy summary.",
            diagnostics,
        )

    start = parse_time(owner_span.get("start_time"), "start_time")
    end = parse_time(owner_span.get("end_time"), "end_time")
    try:
        return AgentExecutionSummary(
            trace_id=trace_id,
            agent_span_id=span_id,
            service=_service_identity(owner_span),
            agent_key=_required_summary_value(agent_key, "junjo.agent.key"),
            agent_name=_required_summary_value(agent_name, "junjo.agent.name"),
            structural_id=_required_summary_value(structural_id, "junjo.executable_structural_id"),
            definition_id=_required_summary_value(definition_id, "junjo.executable_definition_id"),
            runtime_id=_required_summary_value(runtime_id, "junjo.executable_runtime_id"),
            start_time=start,
            end_time=end,
            duration_ns=duration_ns(owner_span, start, end),
            outcome=outcome,
            termination_reason=termination,
            limits=AgentLimits(
                model_requests=_required_summary_value(
                    model_limit, "junjo.agent.limit.model_requests"
                ),
                tool_calls=_required_summary_value(tool_limit, "junjo.agent.limit.tool_calls"),
            ),
            counts=AgentCounts(
                operations=_required_summary_value(operation_count, "junjo.agent.operation.count"),
                model_requests=_required_summary_value(
                    model_count, "junjo.agent.model_request.count"
                ),
                tool_calls=ToolCallCounts(
                    requested=_required_summary_value(
                        requested, "junjo.agent.tool_call.requested_count"
                    ),
                    admitted=_required_summary_value(
                        admitted, "junjo.agent.tool_call.admitted_count"
                    ),
                    started=_required_summary_value(started, "junjo.agent.tool_call.started_count"),
                    completed=_required_summary_value(
                        completed, "junjo.agent.tool_call.completed_count"
                    ),
                ),
            ),
            usage=_required_summary_value(usage, "junjo.agent.usage"),
        )
    except ValueError as error:
        raise AgentEvidenceError(
            "unidentifiable_agent",
            f"Agent summary cannot be represented: {error}",
            diagnostics,
        ) from error


def _operation_sort_key(span: dict[str, Any]) -> tuple[int, int, str]:
    sequence = _attributes(span).get("junjo.agent.operation.sequence")
    if is_contract_int(sequence, minimum=1):
        return (0, sequence, str(span.get("span_id", "")))
    return (1, 0, f"{type(sequence).__name__}:{sequence!r}:{span.get('span_id', '')}")


def _operation_times(span: dict[str, Any]) -> tuple[datetime, datetime, int]:
    start = parse_time(span.get("start_time"), "operation.start_time")
    end = parse_time(span.get("end_time"), "operation.end_time")
    return start, end, duration_ns(span, start, end)


def _model_usage_contract_value(usage: Any) -> dict[str, int]:
    value = {"v": 1}
    fields = {
        "inputTokens": usage.input_tokens,
        "outputTokens": usage.output_tokens,
        "cachedInputTokens": usage.cached_input_tokens,
        "reasoningTokens": usage.reasoning_tokens,
        "totalTokens": usage.total_tokens,
    }
    value.update({key: item for key, item in fields.items() if item is not None})
    return value


def _agent_usage_contract_value(summary: AgentExecutionSummary) -> dict[str, Any]:
    return {
        "v": 1,
        "modelResponses": summary.usage.model_responses,
        "fields": {key: aggregate.model_dump() for key, aggregate in summary.usage.fields.items()},
    }


def _requested_calls(
    response_value: Any,
    tool_spans: list[dict[str, Any]],
    admitted_call_ids: set[str] | None,
    owner_termination: str,
    next_ordinal: int | None,
    definition_context: AgentDefinitionContext | None,
    diagnostics: list[EvidenceDiagnostic],
) -> tuple[list[RequestedToolCall], int | None]:
    if next_ordinal is None:
        return [], None
    if not isinstance(response_value, dict) or response_value.get("type") != "tool_calls":
        return [], next_ordinal
    calls = response_value.get("calls")
    if not isinstance(calls, list):
        diagnostics.append(
            diagnostic(
                "invalid_model_response", "junjo.agent.model.response", "Tool calls are invalid."
            )
        )
        return [], next_ordinal

    projected: list[RequestedToolCall] = []
    for call in calls:
        ordinal = next_ordinal
        next_ordinal += 1
        if not isinstance(call, dict):
            diagnostics.append(
                diagnostic(
                    "tool_call_identity_mismatch", "model.response.calls", "Tool call is invalid."
                )
            )
            continue
        call_id = call.get("id")
        tool_name = call.get("name")
        if (
            not isinstance(call_id, str)
            or not call_id
            or not isinstance(tool_name, str)
            or not tool_name
        ):
            diagnostics.append(
                diagnostic(
                    "tool_call_identity_mismatch",
                    "model.response.calls",
                    "Tool call identity is absent.",
                )
            )
            continue
        matches = [
            span
            for span in tool_spans
            if _attributes(span).get("junjo.agent.tool_call.id") == call_id
            and _attributes(span).get("junjo.agent.tool_call.ordinal") == ordinal
        ]
        observed = len(matches) == 1
        admitted = admitted_call_ids is not None and call_id in admitted_call_ids
        if admitted:
            admission = "admitted"
            reason = None if observed else "execution_interrupted"
        elif admitted_call_ids is None:
            admission = "unknown"
            reason = "store_evidence_unavailable"
        else:
            admission = "not_admitted"
            if observed:
                reason = "tool_input_validation_error"
            elif owner_termination == "unknown_tool":
                reason = (
                    "unknown_tool"
                    if definition_context is not None
                    and tool_name not in definition_context.tool_structural_ids
                    else "batch_preflight_rejected"
                )
            elif owner_termination == "limit_exceeded":
                reason = "limit_exceeded"
            else:
                reason = "batch_preflight_rejected"
        projected.append(
            RequestedToolCall(
                call_id=call_id,
                ordinal=ordinal,
                tool_name=tool_name,
                observed_tool_operation=observed,
                admission=admission,
                reason=reason,
            )
        )
    return projected, next_ordinal


def _model_operation(
    span: dict[str, Any],
    tool_spans: list[dict[str, Any]],
    admitted_call_ids: set[str] | None,
    owner_termination: str,
    next_tool_ordinal: int | None,
    definition_context: AgentDefinitionContext | None,
    diagnostics: list[EvidenceDiagnostic],
) -> tuple[ModelOperation | None, int | None]:
    attributes = _attributes(span)
    validate_operation_transport(span, attributes, diagnostics)
    sequence = required_int(attributes, "junjo.agent.operation.sequence", diagnostics, minimum=1)
    ordinal = required_int(attributes, "junjo.agent.model_request.ordinal", diagnostics, minimum=1)
    revision = required_int(attributes, "junjo.agent.model_request.state_revision", diagnostics)
    driver = required_string(attributes, "junjo.agent.model.driver_key", diagnostics)
    provider = required_string(attributes, "junjo.agent.model.provider", diagnostics)
    model_name = required_string(attributes, "junjo.agent.model.name", diagnostics)
    span_id = span.get("span_id")
    if any(
        value is None for value in (sequence, ordinal, revision, driver, provider, model_name)
    ) or not isinstance(span_id, str):
        return None, next_tool_ordinal

    request, issues = parse_payload_slot(attributes, "junjo.agent.model.request", required=True)
    diagnostics.extend(issues)
    assert request is not None
    validate_model_request(request, attributes, definition_context, diagnostics)
    candidate = parse_candidate(attributes, "junjo.agent.model.response_candidate", diagnostics)
    outcome = operation_outcome(span, attributes)
    candidate_reason = candidate.unavailable_reason
    if (candidate_reason == "cancelled") != (
        outcome == "cancelled" and not candidate.available
    ):
        diagnostics.append(
            diagnostic(
                "invalid_candidate_transport_correspondence",
                "junjo.agent.model.response_candidate",
                "Model candidate availability does not match operation transport.",
            )
        )
    response_type = attributes.get("junjo.agent.model.response_type")
    response_present = payload_slot_present(attributes, "junjo.agent.model.response")
    response = None
    response_content_valid = False
    if (response_type is not None) != response_present:
        diagnostics.append(
            diagnostic(
                "invalid_model_response_evidence",
                "junjo.agent.model.response",
                "Validated Model response type and payload must be present together.",
            )
        )
    if outcome != "completed" and (response_type is not None or response_present):
        diagnostics.append(
            diagnostic(
                "invalid_model_response_transport",
                "junjo.agent.model.response",
                "Failed or cancelled Model operation cannot publish a validated response.",
            )
        )
        response_type = None
        response_present = False
    elif outcome == "completed" and not response_present:
        diagnostics.append(
            diagnostic(
                "invalid_model_response_transport",
                "junjo.agent.model.response",
                "Completed Model operation requires a validated response.",
            )
        )
    if outcome == "completed" and not candidate.available:
        diagnostics.append(
            diagnostic(
                "invalid_candidate_transport_correspondence",
                "junjo.agent.model.response_candidate",
                "Completed Model operation requires an available response candidate.",
            )
        )
    if response_type is not None and response_present:
        if not is_portable_enum(response_type, {"final_output", "tool_calls"}):
            diagnostics.append(
                diagnostic(
                    "invalid_model_response",
                    "junjo.agent.model.response_type",
                    "Model response type is invalid.",
                )
            )
            response_type = None
        else:
            response, issues = parse_payload_slot(
                attributes, "junjo.agent.model.response", required=True
            )
            diagnostics.extend(issues)
            assert response is not None
            response_content_valid = validate_model_response(response, response_type, diagnostics)
    usage = parse_model_usage(attributes, diagnostics)
    if usage is not None and response is None:
        diagnostics.append(
            diagnostic(
                "model_usage_without_response",
                "junjo.agent.model.usage",
                "Model usage requires validated response evidence.",
            )
        )
        usage = None
    if response is not None and response.mode == "full" and response_content_valid:
        response_usage = response.value.get("usage")
        observed_usage = None if usage is None else _model_usage_contract_value(usage)
        if response_usage != observed_usage:
            diagnostics.append(
                diagnostic(
                    "model_usage_mismatch",
                    "junjo.agent.model.usage",
                    "Operation usage does not match its validated response.",
                )
            )
    if response_type == "tool_calls" and response is not None and response.mode != "full":
        requested_calls = []
        next_tool_ordinal = None
    else:
        requested_calls, next_tool_ordinal = _requested_calls(
            response.value if response is not None and response_content_valid else None,
            tool_spans,
            admitted_call_ids,
            owner_termination,
            next_tool_ordinal,
            definition_context,
            diagnostics,
        )
    try:
        start, end, elapsed = _operation_times(span)
    except AgentEvidenceError as error:
        diagnostics.extend(error.diagnostics)
        return None, next_tool_ordinal
    try:
        return (
            ModelOperation(
                operation_type="model_request",
                sequence=sequence,
                span_id=span_id,
                start_time=start,
                end_time=end,
                duration_ns=elapsed,
                ordinal=ordinal,
                state_revision=revision,
                driver_key=driver,
                provider=provider,
                model_name=model_name,
                request=request,
                response_candidate=candidate,
                response_type=response_type,
                response=response,
                usage=usage,
                requested_tool_calls=requested_calls,
                outcome=outcome,
                error=execution_error(span, attributes, diagnostics),
                cancellation=cancellation_evidence(attributes, diagnostics),
            ),
            next_tool_ordinal,
        )
    except ValueError as error:
        diagnostics.append(
            diagnostic("invalid_model_operation", span_evidence_path(span), str(error))
        )
        return None, next_tool_ordinal


def _tool_operation(
    span: dict[str, Any],
    admitted_call_ids: set[str] | None,
    diagnostics: list[EvidenceDiagnostic],
) -> ToolOperation | None:
    attributes = _attributes(span)
    validate_operation_transport(span, attributes, diagnostics)
    sequence = required_int(attributes, "junjo.agent.operation.sequence", diagnostics, minimum=1)
    ordinal = required_int(attributes, "junjo.agent.tool_call.ordinal", diagnostics, minimum=1)
    before = required_int(attributes, "junjo.agent.tool.state_revision.before", diagnostics)
    call_id = required_string(attributes, "junjo.agent.tool_call.id", diagnostics)
    tool_name = required_string(attributes, "junjo.agent.tool.name", diagnostics)
    structural_id = required_string(attributes, "junjo.agent.tool.structural_id", diagnostics)
    span_id = span.get("span_id")
    if any(
        value is None for value in (sequence, ordinal, before, call_id, tool_name, structural_id)
    ) or not isinstance(span_id, str):
        return None
    outcome = operation_outcome(span, attributes)
    after = attributes.get("junjo.agent.tool.state_revision.after")
    if after is not None and not is_contract_int(after):
        diagnostics.append(
            diagnostic(
                "invalid_contract_integer",
                "junjo.agent.tool.state_revision.after",
                "Tool revision-after is invalid.",
            )
        )
        after = None

    requested, issues = parse_payload_slot(
        attributes, "junjo.agent.tool.requested_arguments", required=True
    )
    diagnostics.extend(issues)
    assert requested is not None
    arguments, issues = parse_payload_slot(attributes, "junjo.agent.tool.arguments", required=False)
    diagnostics.extend(issues)
    arguments_published = payload_slot_present(attributes, "junjo.agent.tool.arguments")
    candidate = parse_candidate(attributes, "junjo.agent.tool.result_candidate", diagnostics)
    candidate_reason = candidate.unavailable_reason
    if (candidate_reason == "cancelled") != (
        outcome == "cancelled" and not candidate.available
    ):
        diagnostics.append(
            diagnostic(
                "invalid_candidate_transport_correspondence",
                "junjo.agent.tool.result_candidate",
                "Tool candidate availability does not match operation transport.",
            )
        )
    if admitted_call_ids is not None:
        admitted = call_id in admitted_call_ids
        if (arguments is not None) != admitted:
            diagnostics.append(
                diagnostic(
                    "invalid_tool_argument_admission",
                    "junjo.agent.tool.arguments",
                    "Validated Tool arguments must exactly match replayed admission.",
                )
            )
    started = candidate.available or candidate.unavailable_reason != "not_invoked"
    if started and arguments is None:
        diagnostics.append(
            diagnostic(
                "invalid_tool_started_evidence",
                "junjo.agent.tool.arguments",
                "Started Tool operation requires validated arguments.",
            )
        )
    if (
        attributes.get("error.type") == "AgentToolInputValidationError"
        and arguments_published
    ):
        diagnostics.append(
            diagnostic(
                "unexpected_tool_arguments_evidence",
                "junjo.agent.tool.arguments",
                "Tool input-validation failure cannot publish validated arguments.",
            )
        )
        arguments = None
    result, issues = parse_payload_slot(attributes, "junjo.agent.tool.result", required=False)
    diagnostics.extend(issues)
    result_present = result is not None
    revision_after_present = after is not None
    if result_present != revision_after_present:
        diagnostics.append(
            diagnostic(
                "invalid_tool_result_commit_evidence",
                "junjo.agent.tool.result",
                "Validated Tool result and committed revision must be present together.",
            )
        )
    if outcome != "completed" and (result_present or revision_after_present):
        diagnostics.append(
            diagnostic(
                "invalid_tool_result_transport",
                "junjo.agent.tool.result",
                "Failed or cancelled Tool operation cannot publish committed result evidence.",
            )
        )
        result = None
        after = None
    elif outcome == "completed":
        if arguments is None or result is None or after is None:
            diagnostics.append(
                diagnostic(
                    "invalid_tool_result_transport",
                    "junjo.agent.tool.result",
                    "Completed Tool operation requires arguments, result, and committed revision.",
                )
            )
        if not candidate.available:
            diagnostics.append(
                diagnostic(
                    "invalid_candidate_transport_correspondence",
                    "junjo.agent.tool.result_candidate",
                    "Completed Tool operation requires an available result candidate.",
                )
            )
    try:
        start, end, elapsed = _operation_times(span)
    except AgentEvidenceError as error:
        diagnostics.extend(error.diagnostics)
        return None
    try:
        return ToolOperation(
            operation_type="tool",
            sequence=sequence,
            span_id=span_id,
            start_time=start,
            end_time=end,
            duration_ns=elapsed,
            call_id=call_id,
            ordinal=ordinal,
            tool_name=tool_name,
            tool_structural_id=structural_id,
            state_revision_before=before,
            state_revision_after=after,
            requested_arguments=requested,
            arguments=arguments,
            result_candidate=candidate,
            result=result,
            outcome=outcome,
            error=execution_error(span, attributes, diagnostics),
            cancellation=cancellation_evidence(attributes, diagnostics),
        )
    except ValueError as error:
        diagnostics.append(
            diagnostic("invalid_tool_operation", span_evidence_path(span), str(error))
        )
        return None


def _validate_sequences_and_counts(
    summary: AgentExecutionSummary,
    raw_operations: list[dict[str, Any]],
    operations: list[AgentOperation],
    diagnostics: list[EvidenceDiagnostic],
) -> None:
    sequences = [_attributes(span).get("junjo.agent.operation.sequence") for span in raw_operations]
    integers = [value for value in sequences if is_contract_int(value, minimum=1)]
    if len(integers) != len(sequences):
        diagnostics.append(
            diagnostic(
                "operation_sequence_out_of_range",
                "operations",
                "An operation sequence is invalid.",
            )
        )
    if any(sequence > summary.counts.operations for sequence in integers):
        diagnostics.append(
            diagnostic(
                "operation_sequence_out_of_range",
                "operations",
                "An operation sequence exceeds the owner count.",
            )
        )
    if len(integers) != len(set(integers)):
        diagnostics.append(
            diagnostic(
                "operation_sequence_duplicate", "operations", "Operation sequences duplicate."
            )
        )
    if sorted(integers) != list(range(1, summary.counts.operations + 1)):
        diagnostics.append(
            diagnostic("operation_sequence_gap", "operations", "Operation sequence is incomplete.")
        )

    model_ordinals = [op.ordinal for op in operations if isinstance(op, ModelOperation)]
    if sorted(model_ordinals) != list(range(1, summary.counts.model_requests + 1)):
        diagnostics.append(
            diagnostic(
                "model_ordinal_noncontiguous",
                "operations",
                "Model-request ordinals are not contiguous.",
            )
        )
    if len(raw_operations) != summary.counts.operations:
        diagnostics.append(
            diagnostic(
                "operation_count_mismatch", "operations", "Owner operation count is inconsistent."
            )
        )
    if len(model_ordinals) != summary.counts.model_requests:
        diagnostics.append(
            diagnostic("model_count_mismatch", "operations", "Owner model count is inconsistent.")
        )

    tool_counts = summary.counts.tool_calls
    if (
        not tool_counts.completed
        <= tool_counts.started
        <= tool_counts.admitted
        <= tool_counts.requested
    ):
        diagnostics.append(
            diagnostic(
                "tool_count_inequality", "counts.tool_calls", "Tool counts are inconsistent."
            )
        )
    if tool_counts.admitted > summary.limits.tool_calls:
        diagnostics.append(
            diagnostic(
                "tool_limit_mismatch", "counts.tool_calls", "Admitted Tool count exceeds limit."
            )
        )

    opaque_tool_call_response = any(
        isinstance(operation, ModelOperation)
        and operation.response_type == "tool_calls"
        and operation.response is not None
        and operation.response.mode != "full"
        for operation in operations
    )
    requested_calls = [
        call
        for operation in operations
        if isinstance(operation, ModelOperation)
        for call in operation.requested_tool_calls
    ]
    if not opaque_tool_call_response and len(requested_calls) != tool_counts.requested:
        diagnostics.append(
            diagnostic(
                "tool_call_identity_mismatch",
                "operations.requested_tool_calls",
                "Requested Tool-call count does not reconcile.",
            )
        )
    identities = [(call.call_id, call.ordinal) for call in requested_calls]
    if not opaque_tool_call_response and len(identities) != len(set(identities)):
        diagnostics.append(
            diagnostic(
                "tool_call_identity_mismatch",
                "operations.requested_tool_calls",
                "Requested Tool-call identity duplicates.",
            )
        )
    requested_identity = set(identities)
    tool_identity = {
        (operation.call_id, operation.ordinal)
        for operation in operations
        if isinstance(operation, ToolOperation)
    }
    if not opaque_tool_call_response and not tool_identity <= requested_identity:
        diagnostics.append(
            diagnostic(
                "tool_call_identity_mismatch",
                "operations.tool",
                "Tool operation does not match a requested call.",
            )
        )


def _validate_operation_correspondence(
    summary: AgentExecutionSummary,
    operations: list[AgentOperation],
    definition: AgentDefinitionContext | None,
    admitted_call_ids: set[str] | None,
    diagnostics: list[EvidenceDiagnostic],
) -> None:
    requested: dict[tuple[str, int], dict[str, Any]] = {}
    next_ordinal = 1
    for operation in operations:
        if not isinstance(operation, ModelOperation):
            continue
        response = operation.response
        if (
            response is None
            or response.mode != "full"
            or not isinstance(response.value, dict)
            or response.value.get("type") != "tool_calls"
        ):
            continue
        calls = response.value.get("calls")
        if not isinstance(calls, list):
            continue
        for call in calls:
            if isinstance(call, dict):
                requested[(call.get("id"), next_ordinal)] = call
            next_ordinal += 1

    tool_operations = [
        operation for operation in operations if isinstance(operation, ToolOperation)
    ]
    identities = [(operation.call_id, operation.ordinal) for operation in tool_operations]
    if len(identities) != len(set(identities)):
        diagnostics.append(
            diagnostic(
                "tool_call_identity_mismatch",
                "operations.tool",
                "More than one Tool operation owns the same requested call.",
            )
        )
    for operation in tool_operations:
        call = requested.get((operation.call_id, operation.ordinal))
        mismatch = False
        if call is not None:
            mismatch = operation.tool_name != call.get("name")
            if operation.requested_arguments.mode == "full":
                mismatch = mismatch or operation.requested_arguments.value != call.get("arguments")
        if definition is not None:
            mismatch = mismatch or (
                definition.tool_structural_ids.get(operation.tool_name)
                != operation.tool_structural_id
            )
        if mismatch:
            diagnostics.append(
                diagnostic(
                    "tool_operation_correspondence_mismatch",
                    f"operations[{operation.sequence}]",
                    "Tool operation does not match the requested call and declared Tool.",
                )
            )

    expected_counts = {
        "admitted": (
            len(admitted_call_ids)
            if admitted_call_ids is not None
            else summary.counts.tool_calls.admitted
        ),
        "started": sum(
            operation.arguments is not None
            and (
                operation.result_candidate.available
                or operation.result_candidate.unavailable_reason != "not_invoked"
            )
            for operation in tool_operations
        ),
        "completed": sum(operation.result is not None for operation in tool_operations),
    }
    observed_counts = {
        "admitted": summary.counts.tool_calls.admitted,
        "started": summary.counts.tool_calls.started,
        "completed": summary.counts.tool_calls.completed,
    }
    if expected_counts != observed_counts:
        diagnostics.append(
            diagnostic(
                "tool_count_reconciliation_mismatch",
                "counts.tool_calls",
                "Owner Tool counts do not match realized Tool operation evidence.",
            )
        )

    expected_usage: dict[str, Any] = {"modelResponses": 0, "fields": {}}
    for operation in operations:
        if not isinstance(operation, ModelOperation) or operation.response is None:
            continue
        expected_usage["modelResponses"] += 1
        if operation.usage is None:
            continue
        for field, value in _model_usage_contract_value(operation.usage).items():
            if field == "v":
                continue
            aggregate = expected_usage["fields"].setdefault(field, {"sum": 0, "observations": 0})
            aggregate["sum"] += value
            aggregate["observations"] += 1
    if summary.usage.model_dump(by_alias=True) != {
        "model_responses": expected_usage["modelResponses"],
        "fields": expected_usage["fields"],
    }:
        diagnostics.append(
            diagnostic(
                "agent_usage_mismatch",
                "junjo.agent.usage",
                "Owner usage does not match validated model response evidence.",
            )
        )


def _replayed_admitted_call_ids(
    store_result: Any, diagnostics: list[EvidenceDiagnostic]
) -> set[str] | None:
    state = store_result.detail
    if (
        not store_result.replay_verified
        or state.end is None
        or state.end.mode != "full"
        or not isinstance(state.end.value, dict)
    ):
        return None
    raw_ids = state.end.value.get("admitted_tool_call_ids")
    if (
        not isinstance(raw_ids, list)
        or not all(isinstance(call_id, str) and call_id for call_id in raw_ids)
        or len(raw_ids) != len(set(raw_ids))
    ):
        diagnostics.append(
            diagnostic(
                "invalid_admission_evidence",
                "junjo.agent.state.end.admitted_tool_call_ids",
                "Replayed Tool admission identities are invalid.",
            )
        )
        return None
    return set(raw_ids)


def _owned_store_events(span: dict[str, Any], store_id: str) -> list[dict[str, Any]]:
    events = span.get("events_json")
    if not isinstance(events, list):
        return []
    return [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("name") == "set_state"
        and isinstance(event.get("attributes"), dict)
        and event["attributes"].get("junjo.store.id") == store_id
    ]


def _diagnose_out_of_scope_store_events(
    trace_spans: list[dict[str, Any]],
    eligible_spans: list[dict[str, Any]],
    store_id: Any,
    diagnostics: list[EvidenceDiagnostic],
) -> None:
    """Reject matching Agent Store events attached outside causal owner scopes."""
    if not is_portable_text(store_id, nonempty=True):
        return
    eligible_ids = {
        (span.get("trace_id"), span.get("span_id"))
        for span in eligible_spans
        if is_lower_hex(span.get("trace_id"), length=32)
        and is_lower_hex(span.get("span_id"), length=16)
    }
    for index, span in enumerate(trace_spans):
        span_identity = (span.get("trace_id"), span.get("span_id"))
        if (
            is_lower_hex(span_identity[0], length=32)
            and is_lower_hex(span_identity[1], length=16)
            and span_identity in eligible_ids
        ):
            continue
        if _owned_store_events(span, store_id):
            diagnostics.append(
                diagnostic(
                    "store_causal_owner_mismatch",
                    span_evidence_path(span, "events_json", index=index),
                    "Agent Store transition is attached outside its owner or operation spans.",
                )
            )


def _validate_agent_store_causality(
    owner_span: dict[str, Any],
    operations: list[dict[str, Any]],
    store_id: Any,
    diagnostics: list[EvidenceDiagnostic],
) -> None:
    if not isinstance(store_id, str) or not store_id:
        return
    allowed_owner_actions = {
        "admit_tool_batch",
        "commit_success",
        "set_terminal_reason",
    }
    allowed_operation_actions = {
        "model_request": {"record_model_start", "record_model_response"},
        "tool": {"record_tool_started", "record_tool_result"},
    }
    for span in [owner_span, *operations]:
        attributes = _attributes(span)
        operation_type = attributes.get("junjo.agent.operation_type")
        allowed = (
            allowed_owner_actions
            if span is owner_span
            else (
                allowed_operation_actions.get(operation_type, set())
                if is_portable_enum(operation_type, allowed_operation_actions)
                else set()
            )
        )
        events = _owned_store_events(span, store_id)
        for event in events:
            action = event["attributes"].get("junjo.store.action")
            if not is_portable_enum(action, allowed):
                diagnostics.append(
                    diagnostic(
                        "store_causal_owner_mismatch",
                        span_evidence_path(span, "junjo.store.action"),
                        "Store transition action is attached to the wrong causal span.",
                    )
                )

        if operation_type == "model_request":
            starts = [
                event
                for event in events
                if event["attributes"].get("junjo.store.action") == "record_model_start"
            ]
            expected = attributes.get("junjo.agent.model_request.state_revision")
            if (
                len(starts) != 1
                or starts[0]["attributes"].get("junjo.store.revision.after") != expected
            ):
                diagnostics.append(
                    diagnostic(
                        "model_state_revision_mismatch",
                        span_evidence_path(span),
                        "Model request revision does not match its causal Store transition.",
                    )
                )
            responses = [
                event
                for event in events
                if event["attributes"].get("junjo.store.action")
                == "record_model_response"
            ]
            response_expected = payload_slot_present(
                attributes, "junjo.agent.model.response"
            )
            if (not response_expected and responses) or (
                response_expected and len(responses) != 1
            ):
                diagnostics.append(
                    diagnostic(
                        "model_response_causality_mismatch",
                        span_evidence_path(span),
                        "Model response evidence does not match its causal Store transition.",
                    )
                )
        elif operation_type == "tool":
            started = [
                event
                for event in events
                if event["attributes"].get("junjo.store.action") == "record_tool_started"
            ]
            results = [
                event
                for event in events
                if event["attributes"].get("junjo.store.action") == "record_tool_result"
            ]
            before = attributes.get("junjo.agent.tool.state_revision.before")
            after = attributes.get("junjo.agent.tool.state_revision.after")
            started_expected = (
                attributes.get("junjo.agent.tool.result_candidate.available") is True
                or attributes.get("junjo.agent.tool.result_candidate.unavailable_reason")
                != "not_invoked"
            )
            if (not started_expected and started) or (
                started_expected
                and (
                    len(started) != 1
                    or started[0]["attributes"].get("junjo.store.revision.before") != before
                )
            ):
                diagnostics.append(
                    diagnostic(
                        "tool_state_revision_mismatch",
                        span_evidence_path(span),
                        "Tool start revision does not match its causal Store transition.",
                    )
                )
            result_expected = after is not None or payload_slot_present(
                attributes, "junjo.agent.tool.result"
            )
            if (not result_expected and results) or (
                result_expected
                and (
                    len(results) != 1
                    or results[0]["attributes"].get("junjo.store.revision.after") != after
                )
            ):
                diagnostics.append(
                    diagnostic(
                        "tool_state_revision_mismatch",
                        span_evidence_path(span),
                        "Tool result revision does not match its causal Store transition.",
                    )
                )


def _validate_state_correspondence(
    summary: AgentExecutionSummary,
    state: Any,
    input_evidence: Any,
    output_evidence: Any,
    operations: list[AgentOperation],
    diagnostics: list[EvidenceDiagnostic],
) -> None:
    start = state.start
    end = state.end
    if (
        start is not None
        and start.mode == "full"
        and isinstance(start.value, dict)
        and input_evidence is not None
        and input_evidence.mode == "full"
        and start.value.get("input") != input_evidence.value
    ):
        diagnostics.append(
            diagnostic(
                "state_owner_mismatch",
                "junjo.agent.state.start.input",
                "Store start input does not match owner input evidence.",
            )
        )

    if end is None or end.mode != "full" or not isinstance(end.value, dict):
        return
    expected = {
        "model_request_count": summary.counts.model_requests,
        "tool_call_requested_count": summary.counts.tool_calls.requested,
        "tool_call_admitted_count": summary.counts.tool_calls.admitted,
        "tool_call_started_count": summary.counts.tool_calls.started,
        "tool_call_completed_count": summary.counts.tool_calls.completed,
        "usage": _agent_usage_contract_value(summary),
        "terminal_reason": summary.termination_reason,
    }
    if any(end.value.get(key) != value for key, value in expected.items()):
        diagnostics.append(
            diagnostic(
                "state_owner_mismatch",
                "junjo.agent.state.end",
                "Store terminal counters, usage, or reason do not match owner evidence.",
            )
        )

    final_available = end.value.get("final_output_available")
    final_output = end.value.get("final_output")
    if summary.outcome == "completed":
        if output_evidence is None or final_available is not True:
            diagnostics.append(
                diagnostic(
                    "final_output_mismatch",
                    "junjo.agent.output",
                    "Completed Agent requires owner output and committed Store output evidence.",
                )
            )
        elif output_evidence.mode == "full" and final_output != output_evidence.value:
            diagnostics.append(
                diagnostic(
                    "final_output_mismatch",
                    "junjo.agent.output",
                    "Inspectable owner output does not match the committed Store output.",
                )
            )
        final_response_operations = [
            operation
            for operation in operations
            if isinstance(operation, ModelOperation)
            and operation.response_type == "final_output"
            and operation.response is not None
        ]
        if len(final_response_operations) != 1:
            diagnostics.append(
                diagnostic(
                    "final_output_mismatch",
                    "operations.model.response.output",
                    "Completed Agent requires exactly one normalized final model response.",
                )
            )
    elif final_available is not False or final_output is not None:
        diagnostics.append(
            diagnostic(
                "final_output_mismatch",
                "junjo.agent.state.end.final_output",
                "Non-completed Agent Store cannot contain committed final output.",
            )
        )


def _nested_executables(
    owner_span: dict[str, Any],
    spans: list[dict[str, Any]],
    eligible_operations: list[dict[str, Any]],
    diagnostics: list[EvidenceDiagnostic],
) -> list[NestedExecutableReference]:
    """Project only executable spans directly parented by an owned Tool operation."""
    tool_parents: dict[str, int] = {}
    for operation in eligible_operations:
        attributes = _attributes(operation)
        if attributes.get("junjo.agent.operation_type") != "tool":
            continue
        span_id = operation.get("span_id")
        sequence = attributes.get("junjo.agent.operation.sequence")
        if not isinstance(span_id, str) or not is_contract_int(sequence, minimum=1):
            continue
        tool_parents[span_id] = sequence

    owner_trace_id = owner_span.get("trace_id")
    owner_attributes = _attributes(owner_span)
    nested: list[NestedExecutableReference] = []
    for span in spans:
        attributes = _attributes(span)
        executable_type = attributes.get("junjo.span_type")
        parent_span_id = span.get("parent_span_id")
        if (
            not is_portable_text(parent_span_id, nonempty=True)
            or parent_span_id not in tool_parents
        ):
            continue
        if not is_portable_enum(executable_type, {"workflow", "agent"}):
            if executable_type is not None and not is_portable_text(executable_type, nonempty=True):
                diagnostics.append(
                    diagnostic(
                        "invalid_nested_executable",
                        span_evidence_path(span, "junjo.span_type"),
                        "Nested executable type is invalid.",
                    )
                )
            continue
        if not require_active_contract(attributes, owner=False, diagnostics=diagnostics):
            continue
        if span.get("trace_id") != owner_trace_id:
            diagnostics.append(
                diagnostic(
                    "invalid_nested_executable_parent",
                    span_evidence_path(span, "trace_id"),
                    "Nested executable is not in its parent Agent trace.",
                )
            )
            continue
        expected_parent = {
            "junjo.parent_executable_type": "agent",
            "junjo.parent_executable_definition_id": owner_attributes.get(
                "junjo.executable_definition_id"
            ),
            "junjo.parent_executable_runtime_id": owner_attributes.get(
                "junjo.executable_runtime_id"
            ),
            "junjo.parent_executable_structural_id": owner_attributes.get(
                "junjo.executable_structural_id"
            ),
        }
        if any(attributes.get(key) != value for key, value in expected_parent.items()):
            diagnostics.append(
                diagnostic(
                    "nested_parent_correspondence_mismatch",
                    span_evidence_path(span, "parent_executable"),
                    "Nested executable semantic parent does not match the owning Agent.",
                )
            )
            continue
        name = (
            attributes.get("junjo.agent.name") if executable_type == "agent" else span.get("name")
        )
        exact_strings = {
            "trace_id": span.get("trace_id"),
            "span_id": span.get("span_id"),
            "definition_id": attributes.get("junjo.executable_definition_id"),
            "runtime_id": attributes.get("junjo.executable_runtime_id"),
            "structural_id": attributes.get("junjo.executable_structural_id"),
            "name": name,
        }
        if not all(is_portable_text(value, nonempty=True) for value in exact_strings.values()):
            diagnostics.append(
                diagnostic(
                    "invalid_nested_executable",
                    span_evidence_path(span),
                    "Nested executable identity contains a missing or non-string value.",
                )
            )
            continue
        try:
            nested.append(
                NestedExecutableReference(
                    executable_type=executable_type,
                    parent_operation_sequence=tool_parents[parent_span_id],
                    parent_operation_span_id=parent_span_id,
                    trace_id=exact_strings["trace_id"],
                    span_id=exact_strings["span_id"],
                    service=_service_identity(span),
                    definition_id=exact_strings["definition_id"],
                    runtime_id=exact_strings["runtime_id"],
                    structural_id=exact_strings["structural_id"],
                    name=exact_strings["name"],
                )
            )
        except (AgentEvidenceError, ValueError) as error:
            diagnostics.append(
                diagnostic(
                    "invalid_nested_executable",
                    span_evidence_path(span),
                    str(error),
                )
            )
    return sorted(
        nested,
        key=lambda item: (
            item.parent_operation_sequence,
            item.parent_operation_span_id,
            item.span_id,
        ),
    )


def _parent_executable(
    owner_span: dict[str, Any],
    spans: list[dict[str, Any]],
    diagnostics: list[EvidenceDiagnostic],
) -> ParentExecutableReference | None:
    owner_attributes = _attributes(owner_span)
    semantic_keys = (
        "junjo.parent_executable_type",
        "junjo.parent_executable_definition_id",
        "junjo.parent_executable_runtime_id",
        "junjo.parent_executable_structural_id",
    )
    parent_span_id = owner_span.get("parent_span_id")
    if parent_span_id is None:
        if any(key in owner_attributes for key in semantic_keys):
            diagnostics.append(
                diagnostic(
                    "parent_executable_correspondence_mismatch",
                    "owner.parent_executable",
                    "Root Agent cannot declare a semantic parent executable.",
                )
            )
        return None
    if not is_lower_hex(parent_span_id, length=16):
        diagnostics.append(
            diagnostic(
                "invalid_parent_executable",
                "owner.parent_span_id",
                "Physical parent span identity is invalid.",
            )
        )
        return None
    declared_values = [owner_attributes.get(key) for key in semantic_keys]
    if not any(value is not None for value in declared_values):
        physical_parent = next(
            (
                span
                for span in spans
                if span.get("trace_id") == owner_span.get("trace_id")
                and span.get("span_id") == parent_span_id
            ),
            None,
        )
        physical_attributes = _attributes(physical_parent) if physical_parent else {}
        if (
            is_portable_enum(
                physical_attributes.get("junjo.span_type"),
                {"workflow", "subflow", "node", "run_concurrent", "agent"},
            )
            or "junjo.agent.operation_type" in physical_attributes
        ):
            diagnostics.append(
                diagnostic(
                    "parent_executable_correspondence_mismatch",
                    "owner.parent_executable",
                    "Agent under a Junjo execution span must declare its semantic parent.",
                )
            )
        return None
    physical_matches = [
        span
        for span in spans
        if span.get("trace_id") == owner_span.get("trace_id")
        and span.get("span_id") == parent_span_id
    ]
    if len(physical_matches) != 1:
        diagnostics.append(
            diagnostic(
                "parent_executable_missing",
                "owner.parent_span_id",
                "Physical parent span evidence is absent or ambiguous.",
            )
        )
        return None
    declared = {
        "executable_type": owner_attributes.get("junjo.parent_executable_type"),
        "definition_id": owner_attributes.get("junjo.parent_executable_definition_id"),
        "runtime_id": owner_attributes.get("junjo.parent_executable_runtime_id"),
        "structural_id": owner_attributes.get("junjo.parent_executable_structural_id"),
    }
    if not is_portable_enum(
        declared["executable_type"],
        {"workflow", "subflow", "node", "run_concurrent", "agent"},
    ) or not all(
        is_portable_text(value, nonempty=True)
        for key, value in declared.items()
        if key != "executable_type"
    ):
        diagnostics.append(
            diagnostic(
                "parent_executable_correspondence_mismatch",
                "owner.parent_executable",
                "Semantic parent executable identity is absent or incomplete.",
            )
        )
        return None
    semantic_matches = []
    for span in spans:
        if span.get("trace_id") != owner_span.get("trace_id"):
            continue
        attributes = _attributes(span)
        if not is_portable_enum(
            attributes.get("junjo.span_type"),
            {"workflow", "subflow", "node", "run_concurrent", "agent"},
        ):
            continue
        if (
            attributes.get("junjo.span_type") == declared["executable_type"]
            and attributes.get("junjo.executable_definition_id") == declared["definition_id"]
            and attributes.get("junjo.executable_runtime_id") == declared["runtime_id"]
            and attributes.get("junjo.executable_structural_id") == declared["structural_id"]
        ):
            semantic_matches.append(span)
    if len(semantic_matches) != 1:
        diagnostics.append(
            diagnostic(
                "parent_executable_correspondence_mismatch",
                "owner.parent_executable",
                "Declared semantic parent does not resolve uniquely in the trace.",
            )
        )
        return None
    parent = semantic_matches[0]
    attributes = _attributes(parent)
    executable_type = attributes["junjo.span_type"]
    if not require_active_contract(attributes, owner=False, diagnostics=diagnostics):
        return None
    physical_parent = physical_matches[0]
    physical_attributes = _attributes(physical_parent)
    physical_operation_type = physical_attributes.get("junjo.agent.operation_type")
    if physical_operation_type is None:
        if physical_parent.get("span_id") != parent.get("span_id"):
            diagnostics.append(
                diagnostic(
                    "parent_executable_correspondence_mismatch",
                    "owner.parent_span_id",
                    "Physical parent must be the declared semantic parent unless an owned Tool operation intervenes.",
                )
            )
            return None
    else:
        physical_parent_is_owned_tool = (
            executable_type == "agent"
            and physical_operation_type == "tool"
            and require_active_contract(
                physical_attributes,
                owner=False,
                diagnostics=diagnostics,
            )
            and physical_parent.get("parent_span_id") == parent.get("span_id")
            and physical_attributes.get("junjo.agent.runtime_id")
            == attributes.get("junjo.executable_runtime_id")
            and physical_attributes.get("junjo.agent.key") == attributes.get("junjo.agent.key")
        )
        if not physical_parent_is_owned_tool:
            diagnostics.append(
                diagnostic(
                    "parent_executable_correspondence_mismatch",
                    "owner.parent_span_id",
                    "Physical Tool parent is not owned by the declared semantic Agent parent.",
                )
            )
            return None
    try:
        name = (
            attributes.get("junjo.agent.name") if executable_type == "agent" else parent.get("name")
        )
        return ParentExecutableReference(
            executable_type=executable_type,
            trace_id=parent.get("trace_id"),
            physical_parent_span_id=parent_span_id,
            span_id=parent.get("span_id"),
            service=_service_identity(parent),
            definition_id=attributes.get("junjo.executable_definition_id"),
            runtime_id=attributes.get("junjo.executable_runtime_id"),
            structural_id=attributes.get("junjo.executable_structural_id"),
            name=name,
        )
    except (AgentEvidenceError, ValueError) as error:
        diagnostics.append(
            diagnostic(
                "invalid_parent_executable",
                "owner.parent_span_id",
                str(error),
            )
        )
        return None


def assemble_agent_detail(
    owner_span: dict[str, Any], trace_spans: list[dict[str, Any]]
) -> AgentExecutionDetail:
    """Assemble one owner-scoped semantic detail from a complete trace."""
    summary = assemble_agent_summary(owner_span)
    attributes = _attributes(owner_span)
    diagnostics: list[EvidenceDiagnostic] = []
    if any(key.startswith("junjo.graph") or key.startswith("junjo.workflow") for key in attributes):
        diagnostics.append(
            diagnostic(
                "agent_graph_evidence_forbidden",
                "owner.attributes",
                "Agent owns no Graph evidence.",
            )
        )
    definition, issues = parse_payload_slot(
        attributes, "junjo.agent.definition_snapshot", required=True
    )
    diagnostics.extend(issues)
    assert definition is not None
    definition_context = validate_definition_snapshot(definition, attributes, diagnostics)

    runtime_id = summary.runtime_id
    raw_operations = [
        span
        for span in trace_spans
        if _attributes(span).get("junjo.agent.runtime_id") == runtime_id
        and "junjo.agent.operation_type" in _attributes(span)
    ]
    eligible_operations: list[dict[str, Any]] = []
    for span in raw_operations:
        operation_attributes = _attributes(span)
        contract_supported = require_active_contract(
            operation_attributes, owner=False, diagnostics=diagnostics
        )
        owner_matches = True
        if span.get("trace_id") != summary.trace_id:
            diagnostics.append(
                diagnostic(
                    "operation_owner_mismatch",
                    span_evidence_path(span, "trace_id"),
                    "Operation trace identity does not match its Agent owner.",
                )
            )
            owner_matches = False
        if operation_attributes.get("junjo.agent.key") != summary.agent_key:
            diagnostics.append(
                diagnostic(
                    "operation_owner_mismatch",
                    span_evidence_path(span, "junjo.agent.key"),
                    "Operation Agent key does not match its owner.",
                )
            )
            owner_matches = False
        if span.get("parent_span_id") != summary.agent_span_id:
            diagnostics.append(
                diagnostic(
                    "operation_owner_mismatch",
                    span_evidence_path(span, "parent_span_id"),
                    "Operation is not a direct child of its Agent owner.",
                )
            )
            owner_matches = False
        if contract_supported and owner_matches:
            eligible_operations.append(span)
    tool_spans = [
        span
        for span in eligible_operations
        if _attributes(span).get("junjo.agent.operation_type") == "tool"
    ]
    store_id = attributes.get("junjo.agent.store.id")
    _diagnose_out_of_scope_store_events(
        trace_spans,
        [owner_span, *eligible_operations],
        store_id,
        diagnostics,
    )
    _validate_agent_store_causality(
        owner_span,
        eligible_operations,
        store_id,
        diagnostics,
    )
    store_result = reconstruct_store(
        attributes,
        [owner_span, *eligible_operations],
        AGENT_STORE_BOUNDARY,
    )
    diagnostics.extend(store_result.diagnostics)
    if (
        summary.termination_reason == "internal_error"
        and attributes.get("error.type") == "AgentInternalError"
        and attributes.get("junjo.agent.state.available") is True
        and store_result.detail.reconstructable_claimed is False
    ):
        diagnostics.append(
            diagnostic(
                "terminal_store_commit_failed",
                "junjo.store.reconstructable",
                "Terminal Store transaction failed; recovered evidence is intentionally partial.",
            )
        )
    admitted_call_ids = _replayed_admitted_call_ids(store_result, diagnostics)

    operations: list[AgentOperation] = []
    next_tool_ordinal = 1
    for span in sorted(eligible_operations, key=_operation_sort_key):
        operation_type = _attributes(span).get("junjo.agent.operation_type")
        if operation_type == "model_request":
            operation, next_tool_ordinal = _model_operation(
                span,
                tool_spans,
                admitted_call_ids,
                summary.termination_reason,
                next_tool_ordinal,
                definition_context,
                diagnostics,
            )
        elif operation_type == "tool":
            operation = _tool_operation(span, admitted_call_ids, diagnostics)
        else:
            diagnostics.append(
                diagnostic(
                    "invalid_operation_type",
                    span_evidence_path(span),
                    "Agent operation type is unsupported.",
                )
            )
            operation = None
        if operation is not None:
            operations.append(operation)
    operations.sort(key=lambda operation: (operation.sequence, operation.span_id))
    _validate_sequences_and_counts(summary, raw_operations, operations, diagnostics)
    _validate_operation_correspondence(
        summary, operations, definition_context, admitted_call_ids, diagnostics
    )
    input_evidence, issues = parse_payload_slot(
        attributes,
        "junjo.agent.input",
        required=attributes.get("junjo.agent.state.available") is True,
    )
    diagnostics.extend(issues)
    if attributes.get("junjo.agent.state.available") is False and input_evidence is not None:
        diagnostics.append(
            diagnostic(
                "unexpected_boundary_input_evidence",
                "junjo.agent.input",
                "State-unavailable Agent cannot carry validated input evidence.",
            )
        )
        input_evidence = None
    output_evidence, issues = parse_payload_slot(
        attributes,
        "junjo.agent.output",
        required=summary.outcome == "completed",
    )
    diagnostics.extend(issues)
    if summary.outcome != "completed" and output_evidence is not None:
        diagnostics.append(
            diagnostic(
                "unexpected_output_evidence",
                "junjo.agent.output",
                "Non-completed Agent cannot publish validated output evidence.",
            )
        )
        output_evidence = None
    _validate_state_correspondence(
        summary,
        store_result.detail,
        input_evidence,
        output_evidence,
        operations,
        diagnostics,
    )

    candidate_roots = {
        "input_validation_error": "junjo.agent.input_candidate",
        "history_validation_error": "junjo.agent.history_candidate",
    }
    expected_candidate = candidate_roots.get(summary.termination_reason)
    parsed_candidates: dict[str, Any] = {}
    for candidate_root in candidate_roots.values():
        if candidate_root == expected_candidate:
            parsed_candidates[candidate_root] = parse_candidate(
                attributes, candidate_root, diagnostics
            )
        elif candidate_present(attributes, candidate_root):
            diagnostics.append(
                diagnostic(
                    "unexpected_boundary_candidate_evidence",
                    candidate_root,
                    "Candidate evidence is forbidden for this termination reason.",
                )
            )
    input_candidate = parsed_candidates.get("junjo.agent.input_candidate")
    history_candidate = parsed_candidates.get("junjo.agent.history_candidate")

    parent_executable = _parent_executable(owner_span, trace_spans, diagnostics)
    nested_executables = _nested_executables(
        owner_span, trace_spans, eligible_operations, diagnostics
    )
    terminal_error = execution_error(owner_span, attributes, diagnostics)
    terminal_cancellation = cancellation_evidence(attributes, diagnostics)
    evidence_spans = [owner_span, *raw_operations]
    integrity = assemble_evidence_integrity(evidence_spans, diagnostics)
    return AgentExecutionDetail(
        summary=summary,
        definition=definition,
        input=input_evidence,
        output=output_evidence,
        input_candidate=input_candidate,
        history_candidate=history_candidate,
        operations=operations,
        state=store_result.detail,
        parent_executable=parent_executable,
        nested_executables=nested_executables,
        error=terminal_error,
        cancellation=terminal_cancellation,
        integrity=integrity,
    )
