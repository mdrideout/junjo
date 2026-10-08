//! Assemble typed Agent execution diagnostics from preserved OTLP spans.

use std::collections::{BTreeMap, HashMap, HashSet};

use indexmap::IndexMap;
use serde_json::json;

use crate::agent_diagnostics::contract::{
    AgentDefinitionContext, cancellation_evidence, candidate_present, diagnostic, duration_ns,
    exception_type_matches, exception_types, execution_error, model_usage_contract_value,
    operation_outcome, parse_agent_usage, parse_candidate, parse_model_usage, parse_time,
    require_active_contract, require_owner_contract, required_int, required_string,
    status_is_error, validate_definition_snapshot, validate_model_request, validate_model_response,
    validate_operation_transport,
};
use crate::agent_diagnostics::schemas::{
    Admission, AgentCounts, AgentEvidenceError, AgentExecutionDetail, AgentExecutionSummary,
    AgentLimits, AgentOperation, AgentUsage, CandidateEvidence, ExecutableType, ModelOperation,
    ModelOperationType, NestedExecutableReference, NestedExecutableType, Outcome,
    ParentExecutableReference, RequestedToolCall, RequestedToolCallReason, ResponseType,
    ServiceIdentity, TerminationReason, ToolCallCounts, ToolOperation, ToolOperationType,
    UnavailableReason, UsageAggregate, is_structural_id,
};
use crate::json::{Json, JsonObject, display, get, member, values_equal};
use crate::spans::{attributes, resource};
use crate::store_diagnostics::integrity::assemble_evidence_integrity;
use crate::store_diagnostics::payloads::{
    parse_payload_slot, parse_required_payload_slot, payload_slot_present,
};
use crate::store_diagnostics::reconstruction::{
    AGENT_APPLICATION_STORE_BOUNDARY, AGENT_STORE_BOUNDARY, StoreReconstructionResult,
    StoreSpanIndex, index_store_spans, owned_store_events, reconstruct_store, store_evidence_spans,
};
use crate::store_diagnostics::schemas::{
    EvidenceDiagnostic, PayloadEvidence, PayloadMode, StoreDetail,
};
use crate::telemetry_contract::{
    contract_int, is_lower_hex, lower_hex, nonempty_text, portable_enum, span_evidence_path,
};
use crate::timestamps::Timestamp;

const OPERATION_TYPE: &str = "junjo.agent.operation_type";
const OPERATION_SEQUENCE: &str = "junjo.agent.operation.sequence";

fn service_identity(span: &JsonObject) -> Result<ServiceIdentity, AgentEvidenceError> {
    let resource = resource(span);
    let invalid = |headline: &str, path: &str, detail: &str| {
        AgentEvidenceError::unidentifiable(
            headline,
            vec![diagnostic("required_identity_missing", path, detail)],
        )
    };
    let Some(name) = nonempty_text(get(resource, "service.name")) else {
        return Err(invalid(
            "Agent resource service.name is absent or invalid.",
            "resource.service.name",
            "Service name is absent or invalid.",
        ));
    };
    // An absent namespace is the explicit empty namespace.
    let namespace = match resource.get("service.namespace") {
        None => "",
        Some(Json::String(namespace)) => namespace,
        Some(_) => {
            return Err(invalid(
                "Agent resource service.namespace is invalid.",
                "resource.service.namespace",
                "Service namespace is invalid.",
            ));
        }
    };
    let version = match get(resource, "service.version") {
        Json::Null => None,
        version => match nonempty_text(version) {
            Some(version) => Some(version.to_string()),
            None => {
                return Err(invalid(
                    "Agent resource service.version is invalid.",
                    "resource.service.version",
                    "Service version is invalid.",
                ));
            }
        },
    };
    Ok(ServiceIdentity {
        namespace: namespace.to_string(),
        name: name.to_string(),
        version,
    })
}

fn is_true(value: &Json) -> bool {
    value == &Json::Bool(true)
}

/// A number or boolean as a quantity, for arithmetic on untrusted facts.
fn quantity(value: &Json) -> Option<f64> {
    match value {
        Json::Bool(value) => Some(f64::from(u8::from(*value))),
        Json::Number(number) => number.as_f64(),
        _ => None,
    }
}

fn validate_owner_terminal_transport(
    owner_span: &JsonObject,
    attributes: &JsonObject,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) {
    let status_is_error = status_is_error(owner_span);
    let has_error_type = attributes.contains_key("error.type");
    let cancelled = is_true(get(attributes, "junjo.cancelled"));
    match get(attributes, "junjo.agent.outcome").as_str() {
        Some("failed") => {
            let matches =
                exception_type_matches(get(attributes, "error.type"), &exception_types(owner_span));
            if !status_is_error || !matches {
                diagnostics.push(diagnostic(
                    "invalid_failure_evidence",
                    "owner.status",
                    "Failed Agent requires matching error status, type, and exception evidence.",
                ));
            }
            if cancelled {
                diagnostics.push(diagnostic(
                    "invalid_failure_evidence",
                    "junjo.cancelled",
                    "Failed Agent cannot also be execution-cancelled.",
                ));
            }
        }
        Some("cancelled") => {
            let has_reason = nonempty_text(get(attributes, "junjo.cancelled_reason")).is_some();
            if !cancelled || !has_reason || status_is_error || has_error_type {
                diagnostics.push(diagnostic(
                    "invalid_cancellation_evidence",
                    "junjo.cancelled",
                    "Cancelled Agent requires a reason and non-error transport ownership.",
                ));
            }
        }
        Some("completed") if status_is_error || has_error_type || cancelled => {
            diagnostics.push(diagnostic(
                "invalid_completion_evidence",
                "owner.status",
                "Completed Agent cannot carry execution failure or cancellation evidence.",
            ));
        }
        _ => {}
    }
}

fn validate_limit_evidence(attributes: &JsonObject, diagnostics: &mut Vec<EvidenceDiagnostic>) {
    const EXCEEDED: &str = "junjo.agent.limit.exceeded";
    const ATTEMPTED: &str = "junjo.agent.limit.attempted_count";
    const BATCH_SIZE: &str = "junjo.agent.limit.requested_batch_size";
    if get(attributes, "junjo.agent.termination_reason").as_str() != Some("limit_exceeded") {
        if [EXCEEDED, ATTEMPTED, BATCH_SIZE]
            .iter()
            .any(|key| attributes.contains_key(*key))
        {
            diagnostics.push(diagnostic(
                "unexpected_limit_evidence",
                "junjo.agent.limit",
                "Limit-exceeded evidence exists on a different terminal reason.",
            ));
        }
        return;
    }

    let exceeded = portable_enum(get(attributes, EXCEEDED), &["model_requests", "tool_calls"]);
    let attempted = contract_int(get(attributes, ATTEMPTED), 1);
    let (Some(exceeded), Some(attempted)) = (exceeded, attempted) else {
        diagnostics.push(diagnostic(
            "invalid_limit_evidence",
            "junjo.agent.limit",
            "Limit-exceeded kind or attempted count is invalid.",
        ));
        return;
    };
    if exceeded == "model_requests" {
        let count = get(attributes, "junjo.agent.model_request.count");
        let limit = get(attributes, "junjo.agent.limit.model_requests");
        // The attempt that hit the limit is the one after the last request.
        let reconciles = values_equal(count, limit)
            && quantity(count).is_some_and(|count| count + 1.0 == attempted as f64)
            && !attributes.contains_key(BATCH_SIZE);
        if !reconciles {
            diagnostics.push(diagnostic(
                "invalid_limit_evidence",
                "junjo.agent.limit",
                "Model-request limit evidence does not reconcile.",
            ));
        }
        return;
    }
    let facts = (
        contract_int(get(attributes, BATCH_SIZE), 1),
        contract_int(get(attributes, "junjo.agent.tool_call.requested_count"), 0),
        contract_int(get(attributes, "junjo.agent.tool_call.admitted_count"), 0),
        contract_int(get(attributes, "junjo.agent.limit.tool_calls"), 1),
    );
    let reconciles = matches!(
        facts,
        (Some(batch_size), Some(requested), Some(admitted), Some(limit))
            if requested > limit && attempted == admitted + batch_size
    );
    if !reconciles {
        diagnostics.push(diagnostic(
            "invalid_limit_evidence",
            "junjo.agent.limit",
            "Tool-call limit evidence does not reconcile.",
        ));
    }
}

/// Validate owner-only iff rules before emitting a summary without
/// integrity.
fn validate_owner_conditional_evidence(
    attributes: &JsonObject,
    usage: Option<&AgentUsage>,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) {
    const AVAILABLE: &str = "junjo.agent.state.available";
    let state_available = get(attributes, AVAILABLE).as_bool();
    let termination = get(attributes, "junjo.agent.termination_reason").as_str();
    let expected_outcome = match termination {
        Some("final_output") => "completed",
        Some("cancelled") => "cancelled",
        _ => "failed",
    };
    if get(attributes, "junjo.agent.outcome").as_str() != Some(expected_outcome) {
        diagnostics.push(diagnostic(
            "terminal_outcome_reason_mismatch",
            "junjo.agent.termination_reason",
            "Agent outcome does not match its termination reason.",
        ));
    }
    // State exists from admission onwards. Only a boundary rejection or an
    // admission failure ends an Agent before that.
    let ended_before_admission = matches!(
        termination,
        Some("input_validation_error" | "history_validation_error")
    ) || (termination == Some("internal_error")
        && get(attributes, "error.type").as_str() == Some("AgentAdmissionError"));
    match state_available {
        None => diagnostics.push(diagnostic(
            "invalid_state_availability",
            AVAILABLE,
            "Agent state availability is absent or invalid.",
        )),
        Some(true) => {}
        Some(false) => {
            if !ended_before_admission {
                diagnostics.push(diagnostic(
                    "invalid_unavailable_agent_state",
                    AVAILABLE,
                    "State may be unavailable only before Agent admission.",
                ));
            }
            let has_activity = [
                "junjo.agent.operation.count",
                "junjo.agent.model_request.count",
                "junjo.agent.tool_call.requested_count",
                "junjo.agent.tool_call.admitted_count",
                "junjo.agent.tool_call.started_count",
                "junjo.agent.tool_call.completed_count",
            ]
            .iter()
            .any(|key| !values_equal(get(attributes, key), &json!(0)));
            let empty_usage =
                usage.is_some_and(|usage| usage.model_responses == 0 && usage.fields.is_empty());
            if has_activity || !empty_usage {
                diagnostics.push(diagnostic(
                    "invalid_unavailable_agent_activity",
                    AVAILABLE,
                    "State-unavailable Agent cannot carry operation, count, or usage activity.",
                ));
            }
        }
    }
    if ended_before_admission && state_available != Some(false) {
        diagnostics.push(diagnostic(
            "invalid_unavailable_agent_state",
            AVAILABLE,
            "Boundary rejection and admission failure require unavailable state.",
        ));
    }
    let requested = contract_int(get(attributes, "junjo.agent.tool_call.requested_count"), 0);
    let tool_limit = contract_int(get(attributes, "junjo.agent.limit.tool_calls"), 1);
    let terminated_on_tool_limit = termination == Some("limit_exceeded")
        && get(attributes, "junjo.agent.limit.exceeded").as_str() == Some("tool_calls");
    if let (Some(requested), Some(tool_limit)) = (requested, tool_limit)
        && requested > tool_limit
        && !terminated_on_tool_limit
    {
        diagnostics.push(diagnostic(
            "invalid_limit_evidence",
            "junjo.agent.limit",
            "Requested Tool count above the limit requires Tool-limit termination evidence.",
        ));
    }
}

/// Build one owner-only summary; no descendant inference is required.
///
/// A list result has no integrity envelope, so questionable owner semantics
/// are never discarded here: malformed owner facts are rejected explicitly.
pub fn assemble_agent_summary(
    owner_span: &JsonObject,
) -> Result<AgentExecutionSummary, AgentEvidenceError> {
    let attributes = attributes(owner_span);
    if get(attributes, "junjo.span_type").as_str() != Some("agent") {
        let issue = diagnostic(
            "invalid_agent_owner_type",
            "junjo.span_type",
            "The selected span is not an Agent.",
        );
        return Err(AgentEvidenceError::unidentifiable(
            issue.message.clone(),
            vec![issue],
        ));
    }
    require_owner_contract(attributes)?;

    let mut diagnostics = Vec::new();
    let trace_id = lower_hex(get(owner_span, "trace_id"), 32);
    let span_id = lower_hex(get(owner_span, "span_id"), 16);
    if trace_id.is_none() {
        diagnostics.push(diagnostic(
            "invalid_trace_id",
            "trace_id",
            "Agent trace identity must be exact lowercase hexadecimal text.",
        ));
    }
    if span_id.is_none() {
        diagnostics.push(diagnostic(
            "invalid_span_id",
            "span_id",
            "Agent span identity must be exact lowercase hexadecimal text.",
        ));
    }
    let (Some(trace_id), Some(span_id)) = (trace_id, span_id) else {
        return Err(AgentEvidenceError::unidentifiable(
            "Agent trace/span identity is absent or invalid.",
            diagnostics,
        ));
    };

    let agent_key = required_string(attributes, "junjo.agent.key", &mut diagnostics);
    let agent_name = required_string(attributes, "junjo.agent.name", &mut diagnostics);
    let structural_id = required_string(
        attributes,
        "junjo.executable_structural_id",
        &mut diagnostics,
    );
    if structural_id.is_some_and(|id| !is_structural_id(id, "agent_sha256:")) {
        diagnostics.push(diagnostic(
            "invalid_agent_structural_id",
            "junjo.executable_structural_id",
            "Agent structural identity is invalid.",
        ));
    }
    let definition_id = required_string(
        attributes,
        "junjo.executable_definition_id",
        &mut diagnostics,
    );
    let runtime_id = required_string(attributes, "junjo.executable_runtime_id", &mut diagnostics);
    let agent_runtime_id = get(attributes, "junjo.agent.runtime_id");
    let runtime_ids_match = match runtime_id {
        Some(runtime_id) => agent_runtime_id.as_str() == Some(runtime_id),
        None => agent_runtime_id.is_null(),
    };
    if !runtime_ids_match {
        diagnostics.push(diagnostic(
            "runtime_identity_mismatch",
            "junjo.agent.runtime_id",
            "Agent runtime IDs do not match.",
        ));
    }

    let model_limit = required_int(
        attributes,
        "junjo.agent.limit.model_requests",
        &mut diagnostics,
        1,
    );
    let tool_limit = required_int(
        attributes,
        "junjo.agent.limit.tool_calls",
        &mut diagnostics,
        1,
    );
    let operation_count = required_int(
        attributes,
        "junjo.agent.operation.count",
        &mut diagnostics,
        0,
    );
    let model_count = required_int(
        attributes,
        "junjo.agent.model_request.count",
        &mut diagnostics,
        0,
    );
    let requested = required_int(
        attributes,
        "junjo.agent.tool_call.requested_count",
        &mut diagnostics,
        0,
    );
    let admitted = required_int(
        attributes,
        "junjo.agent.tool_call.admitted_count",
        &mut diagnostics,
        0,
    );
    let started = required_int(
        attributes,
        "junjo.agent.tool_call.started_count",
        &mut diagnostics,
        0,
    );
    let completed = required_int(
        attributes,
        "junjo.agent.tool_call.completed_count",
        &mut diagnostics,
        0,
    );
    let usage = parse_agent_usage(attributes, &mut diagnostics);
    let tool_calls = match (requested, admitted, started, completed) {
        (Some(requested), Some(admitted), Some(started), Some(completed)) => Some(ToolCallCounts {
            requested,
            admitted,
            started,
            completed,
        }),
        _ => None,
    };
    if tool_calls.is_some_and(|counts| !counts.is_monotonic()) {
        diagnostics.push(diagnostic(
            "tool_count_inequality",
            "counts.tool_calls",
            "Tool counts are inconsistent.",
        ));
    }
    if let (Some(admitted), Some(tool_limit)) = (admitted, tool_limit)
        && admitted > tool_limit
    {
        diagnostics.push(diagnostic(
            "tool_limit_mismatch",
            "counts.tool_calls",
            "Admitted Tool count exceeds limit.",
        ));
    }

    let outcome = portable_enum(get(attributes, "junjo.agent.outcome"), &Outcome::NAMES)
        .and_then(Outcome::from_name);
    let termination = nonempty_text(get(attributes, "junjo.agent.termination_reason"));
    let (Some(outcome), Some(termination)) = (outcome, termination) else {
        diagnostics.push(diagnostic(
            "invalid_terminal_fact",
            "junjo.agent.outcome",
            "Outcome is invalid.",
        ));
        return Err(AgentEvidenceError::unidentifiable(
            "Agent terminal identity is invalid.",
            diagnostics,
        ));
    };
    validate_owner_terminal_transport(owner_span, attributes, &mut diagnostics);
    validate_limit_evidence(attributes, &mut diagnostics);
    validate_owner_conditional_evidence(attributes, usage.as_ref(), &mut diagnostics);

    let facts = (
        (
            agent_key,
            agent_name,
            structural_id,
            definition_id,
            runtime_id,
        ),
        (
            model_limit,
            tool_limit,
            operation_count,
            model_count,
            tool_calls,
        ),
        usage,
    );
    let (
        (
            Some(agent_key),
            Some(agent_name),
            Some(structural_id),
            Some(definition_id),
            Some(runtime_id),
        ),
        (
            Some(model_limit),
            Some(tool_limit),
            Some(operation_count),
            Some(model_count),
            Some(tool_calls),
        ),
        Some(usage),
    ) = facts
    else {
        return Err(untrustworthy_summary(diagnostics));
    };
    if !diagnostics.is_empty() {
        return Err(untrustworthy_summary(diagnostics));
    }

    let start = parse_time(get(owner_span, "start_time"), "start_time")?;
    let end = parse_time(get(owner_span, "end_time"), "end_time")?;
    let unrepresentable = |reason: &str| {
        AgentEvidenceError::unidentifiable(
            format!("Agent summary cannot be represented: {reason}."),
            Vec::new(),
        )
    };
    let summary = AgentExecutionSummary {
        trace_id: trace_id.to_string(),
        agent_span_id: span_id.to_string(),
        service: service_identity(owner_span)?,
        agent_key: agent_key.to_string(),
        agent_name: agent_name.to_string(),
        structural_id: structural_id.to_string(),
        definition_id: definition_id.to_string(),
        runtime_id: runtime_id.to_string(),
        start_time: start,
        end_time: end,
        duration_ns: duration_ns(owner_span, &start, &end)?,
        outcome,
        termination_reason: TerminationReason::from_name(termination)
            .ok_or_else(|| unrepresentable("the termination reason is not a known reason"))?,
        limits: AgentLimits {
            model_requests: model_limit,
            tool_calls: tool_limit,
        },
        counts: AgentCounts {
            operations: operation_count,
            model_requests: model_count,
            tool_calls,
        },
        usage,
    };
    summary.validate().map_err(unrepresentable)?;
    Ok(summary)
}

fn untrustworthy_summary(diagnostics: Vec<EvidenceDiagnostic>) -> AgentEvidenceError {
    AgentEvidenceError::unidentifiable(
        "Agent owner evidence cannot produce a trustworthy summary.",
        diagnostics,
    )
}

/// Order operations by sequence, with the span breaking ties. Operations
/// without a usable sequence follow in a stable order; each is diagnosed and
/// none becomes an operation.
fn operation_sort_key(span: &JsonObject) -> (u8, i64, String) {
    let sequence = get(attributes(span), OPERATION_SEQUENCE);
    let span_id = match span.get("span_id") {
        None => String::new(),
        Some(Json::String(span_id)) => span_id.clone(),
        Some(other) => display(other),
    };
    match contract_int(sequence, 1) {
        Some(sequence) => (0, sequence, span_id),
        None => {
            let kind = match sequence {
                Json::Null => "NoneType",
                Json::Bool(_) => "bool",
                Json::Number(number) if number.is_f64() => "float",
                Json::Number(_) => "int",
                Json::String(_) => "str",
                Json::Array(_) => "list",
                Json::Object(_) => "dict",
            };
            (1, 0, format!("{kind}:{}:{span_id}", display(sequence)))
        }
    }
}

fn operation_times(span: &JsonObject) -> Result<(Timestamp, Timestamp, i64), AgentEvidenceError> {
    let start = parse_time(get(span, "start_time"), "operation.start_time")?;
    let end = parse_time(get(span, "end_time"), "operation.end_time")?;
    let elapsed = duration_ns(span, &start, &end)?;
    Ok((start, end, elapsed))
}

/// The usage payload the Store's terminal state would carry for a summary.
fn agent_usage_contract_value(usage: &AgentUsage) -> Json {
    let fields: JsonObject = usage
        .fields
        .iter()
        .map(|(field, aggregate)| {
            (
                field.contract_name().to_string(),
                json!({"sum": aggregate.sum, "observations": aggregate.observations}),
            )
        })
        .collect();
    json!({"v": 1, "modelResponses": usage.model_responses, "fields": fields})
}

/// What Store replay proved about Tool admission. `None` means the Store
/// could not be replayed, so admission is unknown rather than denied.
type AdmittedCallIds<'a> = Option<&'a HashSet<String>>;

/// Project each call a validated Tool-calls response requested.
///
/// Tool ordinals count every requested call across the whole execution, in
/// order. `next_ordinal` is `None` once an opaque response has made later
/// ordinals unknowable.
fn requested_calls(
    response_value: Option<&Json>,
    tool_spans: &[&JsonObject],
    admitted_call_ids: AdmittedCallIds<'_>,
    owner_termination: TerminationReason,
    next_ordinal: Option<i64>,
    definition_context: Option<&AgentDefinitionContext>,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> (Vec<RequestedToolCall>, Option<i64>) {
    let Some(mut next_ordinal) = next_ordinal else {
        return (Vec::new(), None);
    };
    let response = response_value
        .and_then(Json::as_object)
        .filter(|response| get(response, "type").as_str() == Some("tool_calls"));
    let Some(response) = response else {
        return (Vec::new(), Some(next_ordinal));
    };
    let Some(calls) = get(response, "calls").as_array() else {
        diagnostics.push(diagnostic(
            "invalid_model_response",
            "junjo.agent.model.response",
            "Tool calls are invalid.",
        ));
        return (Vec::new(), Some(next_ordinal));
    };

    let mut projected = Vec::new();
    for call in calls {
        let ordinal = next_ordinal;
        next_ordinal += 1;
        let Some(call) = call.as_object() else {
            diagnostics.push(diagnostic(
                "tool_call_identity_mismatch",
                "model.response.calls",
                "Tool call is invalid.",
            ));
            continue;
        };
        let identity = (
            nonempty_text(get(call, "id")),
            nonempty_text(get(call, "name")),
        );
        let (Some(call_id), Some(tool_name)) = identity else {
            diagnostics.push(diagnostic(
                "tool_call_identity_mismatch",
                "model.response.calls",
                "Tool call identity is absent.",
            ));
            continue;
        };
        let matches = tool_spans
            .iter()
            .filter(|span| {
                let attributes = attributes(span);
                get(attributes, "junjo.agent.tool_call.id").as_str() == Some(call_id)
                    && values_equal(
                        get(attributes, "junjo.agent.tool_call.ordinal"),
                        &json!(ordinal),
                    )
            })
            .count();
        let observed = matches == 1;
        let (admission, reason) = match admitted_call_ids {
            Some(admitted) if admitted.contains(call_id) => (
                Admission::Admitted,
                (!observed).then_some(RequestedToolCallReason::ExecutionInterrupted),
            ),
            None => (
                Admission::Unknown,
                Some(RequestedToolCallReason::StoreEvidenceUnavailable),
            ),
            Some(_) => {
                let reason = if observed {
                    RequestedToolCallReason::ToolInputValidationError
                } else {
                    match owner_termination {
                        TerminationReason::UnknownTool
                            if definition_context.is_some_and(|definition| {
                                !definition.tool_structural_ids.contains_key(tool_name)
                            }) =>
                        {
                            RequestedToolCallReason::UnknownTool
                        }
                        TerminationReason::LimitExceeded => RequestedToolCallReason::LimitExceeded,
                        _ => RequestedToolCallReason::BatchPreflightRejected,
                    }
                };
                (Admission::NotAdmitted, Some(reason))
            }
        };
        projected.push(RequestedToolCall {
            call_id: call_id.to_string(),
            ordinal,
            tool_name: tool_name.to_string(),
            observed_tool_operation: observed,
            admission,
            reason,
        });
    }
    (projected, Some(next_ordinal))
}

/// An unavailable candidate says "cancelled" exactly when the operation was.
fn candidate_matches_cancellation(candidate: &CandidateEvidence, outcome: Outcome) -> bool {
    let says_cancelled = candidate.unavailable_reason == Some(UnavailableReason::Cancelled);
    says_cancelled == (outcome == Outcome::Cancelled && !candidate.available)
}

/// Context shared by every operation of one Agent execution.
struct OperationContext<'a> {
    tool_spans: &'a [&'a JsonObject],
    admitted_call_ids: AdmittedCallIds<'a>,
    owner_termination: TerminationReason,
    definition: Option<&'a AgentDefinitionContext>,
}

fn model_operation(
    span: &JsonObject,
    context: &OperationContext<'_>,
    next_tool_ordinal: Option<i64>,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> (Option<ModelOperation>, Option<i64>) {
    const RESPONSE: &str = "junjo.agent.model.response";
    const CANDIDATE: &str = "junjo.agent.model.response_candidate";
    let attributes = attributes(span);
    validate_operation_transport(span, attributes, diagnostics);
    let facts = (
        required_int(attributes, OPERATION_SEQUENCE, diagnostics, 1),
        required_int(
            attributes,
            "junjo.agent.model_request.ordinal",
            diagnostics,
            1,
        ),
        required_int(
            attributes,
            "junjo.agent.model_request.state_revision",
            diagnostics,
            0,
        ),
        required_string(attributes, "junjo.agent.model.driver_key", diagnostics),
        required_string(attributes, "junjo.agent.model.provider", diagnostics),
        required_string(attributes, "junjo.agent.model.name", diagnostics),
        get(span, "span_id").as_str(),
    );
    let (
        Some(sequence),
        Some(ordinal),
        Some(state_revision),
        Some(driver_key),
        Some(provider),
        Some(model_name),
        Some(span_id),
    ) = facts
    else {
        return (None, next_tool_ordinal);
    };

    let request = parse_required_payload_slot(attributes, "junjo.agent.model.request", diagnostics);
    validate_model_request(&request, attributes, context.definition, diagnostics);
    let candidate = parse_candidate(attributes, CANDIDATE, diagnostics);
    let outcome = operation_outcome(span, attributes);
    if !candidate_matches_cancellation(&candidate, outcome) {
        diagnostics.push(diagnostic(
            "invalid_candidate_transport_correspondence",
            CANDIDATE,
            "Model candidate availability does not match operation transport.",
        ));
    }

    // The declared type and the payload slot are tracked as found, so that an
    // operation carrying one without the other is rejected below.
    let mut declared_type = get(attributes, "junjo.agent.model.response_type");
    let mut response_present = payload_slot_present(attributes, RESPONSE);
    if declared_type.is_null() == response_present {
        diagnostics.push(diagnostic(
            "invalid_model_response_evidence",
            RESPONSE,
            "Validated Model response type and payload must be present together.",
        ));
    }
    if outcome != Outcome::Completed && (!declared_type.is_null() || response_present) {
        diagnostics.push(diagnostic(
            "invalid_model_response_transport",
            RESPONSE,
            "Failed or cancelled Model operation cannot publish a validated response.",
        ));
        declared_type = &Json::Null;
        response_present = false;
    } else if outcome == Outcome::Completed && !response_present {
        diagnostics.push(diagnostic(
            "invalid_model_response_transport",
            RESPONSE,
            "Completed Model operation requires a validated response.",
        ));
    }
    if outcome == Outcome::Completed && !candidate.available {
        diagnostics.push(diagnostic(
            "invalid_candidate_transport_correspondence",
            CANDIDATE,
            "Completed Model operation requires an available response candidate.",
        ));
    }
    let mut response_type = None;
    let mut response = None;
    let mut response_content_valid = false;
    let mut unrepresentable_type = false;
    if !declared_type.is_null() {
        match portable_enum(declared_type, &ResponseType::NAMES).and_then(ResponseType::from_name) {
            Some(parsed) if response_present => {
                let payload = parse_required_payload_slot(attributes, RESPONSE, diagnostics);
                response_content_valid = validate_model_response(&payload, parsed, diagnostics);
                response_type = Some(parsed);
                response = Some(payload);
            }
            Some(parsed) => response_type = Some(parsed),
            None if response_present => diagnostics.push(diagnostic(
                "invalid_model_response",
                "junjo.agent.model.response_type",
                "Model response type is invalid.",
            )),
            None => unrepresentable_type = true,
        }
    }

    let mut usage = parse_model_usage(attributes, diagnostics);
    if usage.is_some() && response.is_none() {
        diagnostics.push(diagnostic(
            "model_usage_without_response",
            "junjo.agent.model.usage",
            "Model usage requires validated response evidence.",
        ));
        usage = None;
    }
    let inspectable_response = response
        .as_ref()
        .filter(|response| response.mode == PayloadMode::Full && response_content_valid);
    if let Some(response) = inspectable_response {
        let observed = usage
            .as_ref()
            .map_or(Json::Null, model_usage_contract_value);
        if !values_equal(member(&response.value, "usage"), &observed) {
            diagnostics.push(diagnostic(
                "model_usage_mismatch",
                "junjo.agent.model.usage",
                "Operation usage does not match its validated response.",
            ));
        }
    }
    let opaque_tool_calls = response_type == Some(ResponseType::ToolCalls)
        && response
            .as_ref()
            .is_some_and(|response| response.mode != PayloadMode::Full);
    let (requested_tool_calls, next_tool_ordinal) = if opaque_tool_calls {
        // The calls cannot be counted, so later Tool ordinals are unknown.
        (Vec::new(), None)
    } else {
        requested_calls(
            response
                .as_ref()
                .filter(|_| response_content_valid)
                .map(|response| &response.value),
            context.tool_spans,
            context.admitted_call_ids,
            context.owner_termination,
            next_tool_ordinal,
            context.definition,
            diagnostics,
        )
    };

    let (start_time, end_time, elapsed) = match operation_times(span) {
        Ok(times) => times,
        Err(error) => {
            diagnostics.extend(error.diagnostics);
            return (None, next_tool_ordinal);
        }
    };
    let error = execution_error(span, attributes, diagnostics);
    let built = cancellation_evidence(attributes, diagnostics).and_then(|cancellation| {
        if unrepresentable_type {
            return Err("the Model response type is not a known type");
        }
        let operation = ModelOperation {
            operation_type: ModelOperationType::ModelRequest,
            sequence,
            span_id: span_id.to_string(),
            start_time,
            end_time,
            duration_ns: elapsed,
            ordinal,
            state_revision,
            driver_key: driver_key.to_string(),
            provider: provider.to_string(),
            model_name: model_name.to_string(),
            request,
            response_candidate: candidate,
            response_type,
            response,
            usage,
            requested_tool_calls,
            outcome,
            error,
            cancellation,
        };
        operation.validate().map(|()| operation)
    });
    match built {
        Ok(operation) => (Some(operation), next_tool_ordinal),
        Err(reason) => {
            diagnostics.push(diagnostic(
                "invalid_model_operation",
                span_evidence_path(span, "", None),
                format!("Model operation cannot be represented: {reason}."),
            ));
            (None, next_tool_ordinal)
        }
    }
}

fn tool_operation(
    span: &JsonObject,
    admitted_call_ids: AdmittedCallIds<'_>,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<ToolOperation> {
    const ARGUMENTS: &str = "junjo.agent.tool.arguments";
    const RESULT: &str = "junjo.agent.tool.result";
    const CANDIDATE: &str = "junjo.agent.tool.result_candidate";
    const REVISION_AFTER: &str = "junjo.agent.tool.state_revision.after";
    let attributes = attributes(span);
    validate_operation_transport(span, attributes, diagnostics);
    let facts = (
        required_int(attributes, OPERATION_SEQUENCE, diagnostics, 1),
        required_int(attributes, "junjo.agent.tool_call.ordinal", diagnostics, 1),
        required_int(
            attributes,
            "junjo.agent.tool.state_revision.before",
            diagnostics,
            0,
        ),
        required_string(attributes, "junjo.agent.tool_call.id", diagnostics),
        required_string(attributes, "junjo.agent.tool.name", diagnostics),
        required_string(attributes, "junjo.agent.tool.structural_id", diagnostics),
        get(span, "span_id").as_str(),
    );
    let (
        Some(sequence),
        Some(ordinal),
        Some(state_revision_before),
        Some(call_id),
        Some(tool_name),
        Some(tool_structural_id),
        Some(span_id),
    ) = facts
    else {
        return None;
    };
    let outcome = operation_outcome(span, attributes);
    let raw_after = get(attributes, REVISION_AFTER);
    let mut state_revision_after = contract_int(raw_after, 0);
    if !raw_after.is_null() && state_revision_after.is_none() {
        diagnostics.push(diagnostic(
            "invalid_contract_integer",
            REVISION_AFTER,
            "Tool revision-after is invalid.",
        ));
    }

    let requested_arguments = parse_required_payload_slot(
        attributes,
        "junjo.agent.tool.requested_arguments",
        diagnostics,
    );
    let mut arguments = parse_payload_slot(attributes, ARGUMENTS, diagnostics);
    let arguments_published = payload_slot_present(attributes, ARGUMENTS);
    let candidate = parse_candidate(attributes, CANDIDATE, diagnostics);
    if !candidate_matches_cancellation(&candidate, outcome) {
        diagnostics.push(diagnostic(
            "invalid_candidate_transport_correspondence",
            CANDIDATE,
            "Tool candidate availability does not match operation transport.",
        ));
    }
    if let Some(admitted) = admitted_call_ids
        && arguments.is_some() != admitted.contains(call_id)
    {
        diagnostics.push(diagnostic(
            "invalid_tool_argument_admission",
            ARGUMENTS,
            "Validated Tool arguments must exactly match replayed admission.",
        ));
    }
    let started =
        candidate.available || candidate.unavailable_reason != Some(UnavailableReason::NotInvoked);
    if started && arguments.is_none() {
        diagnostics.push(diagnostic(
            "invalid_tool_started_evidence",
            ARGUMENTS,
            "Started Tool operation requires validated arguments.",
        ));
    }
    if get(attributes, "error.type").as_str() == Some("AgentToolInputValidationError")
        && arguments_published
    {
        diagnostics.push(diagnostic(
            "unexpected_tool_arguments_evidence",
            ARGUMENTS,
            "Tool input-validation failure cannot publish validated arguments.",
        ));
        arguments = None;
    }
    let mut result = parse_payload_slot(attributes, RESULT, diagnostics);
    if result.is_some() != state_revision_after.is_some() {
        diagnostics.push(diagnostic(
            "invalid_tool_result_commit_evidence",
            RESULT,
            "Validated Tool result and committed revision must be present together.",
        ));
    }
    if outcome != Outcome::Completed && (result.is_some() || state_revision_after.is_some()) {
        diagnostics.push(diagnostic(
            "invalid_tool_result_transport",
            RESULT,
            "Failed or cancelled Tool operation cannot publish committed result evidence.",
        ));
        result = None;
        state_revision_after = None;
    } else if outcome == Outcome::Completed {
        if arguments.is_none() || result.is_none() || state_revision_after.is_none() {
            diagnostics.push(diagnostic(
                "invalid_tool_result_transport",
                RESULT,
                "Completed Tool operation requires arguments, result, and committed revision.",
            ));
        }
        if !candidate.available {
            diagnostics.push(diagnostic(
                "invalid_candidate_transport_correspondence",
                CANDIDATE,
                "Completed Tool operation requires an available result candidate.",
            ));
        }
    }

    let (start_time, end_time, elapsed) = match operation_times(span) {
        Ok(times) => times,
        Err(error) => {
            diagnostics.extend(error.diagnostics);
            return None;
        }
    };
    let error = execution_error(span, attributes, diagnostics);
    let built = cancellation_evidence(attributes, diagnostics).and_then(|cancellation| {
        let operation = ToolOperation {
            operation_type: ToolOperationType::Tool,
            sequence,
            span_id: span_id.to_string(),
            start_time,
            end_time,
            duration_ns: elapsed,
            call_id: call_id.to_string(),
            ordinal,
            tool_name: tool_name.to_string(),
            tool_structural_id: tool_structural_id.to_string(),
            state_revision_before,
            state_revision_after,
            requested_arguments,
            arguments,
            result_candidate: candidate,
            result,
            outcome,
            error,
            cancellation,
        };
        operation.validate().map(|()| operation)
    });
    match built {
        Ok(operation) => Some(operation),
        Err(reason) => {
            diagnostics.push(diagnostic(
                "invalid_tool_operation",
                span_evidence_path(span, "", None),
                format!("Tool operation cannot be represented: {reason}."),
            ));
            None
        }
    }
}

/// Whether sorted values are exactly 1 through `count`.
fn is_one_through(sorted: &[i64], count: i64) -> bool {
    sorted.len() as i64 == count
        && sorted
            .iter()
            .zip(1..)
            .all(|(value, expected)| *value == expected)
}

fn has_duplicates<T: std::hash::Hash + Eq>(items: impl IntoIterator<Item = T>) -> bool {
    let mut seen = HashSet::new();
    !items.into_iter().all(|item| seen.insert(item))
}

fn validate_sequences_and_counts(
    summary: &AgentExecutionSummary,
    raw_operations: &[&JsonObject],
    operations: &[AgentOperation],
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) {
    let mut sequences: Vec<i64> = raw_operations
        .iter()
        .filter_map(|span| contract_int(get(attributes(span), OPERATION_SEQUENCE), 1))
        .collect();
    if sequences.len() != raw_operations.len() {
        diagnostics.push(diagnostic(
            "operation_sequence_out_of_range",
            "operations",
            "An operation sequence is invalid.",
        ));
    }
    if sequences
        .iter()
        .any(|sequence| *sequence > summary.counts.operations)
    {
        diagnostics.push(diagnostic(
            "operation_sequence_out_of_range",
            "operations",
            "An operation sequence exceeds the owner count.",
        ));
    }
    if has_duplicates(sequences.iter()) {
        diagnostics.push(diagnostic(
            "operation_sequence_duplicate",
            "operations",
            "Operation sequences duplicate.",
        ));
    }
    sequences.sort_unstable();
    if !is_one_through(&sequences, summary.counts.operations) {
        diagnostics.push(diagnostic(
            "operation_sequence_gap",
            "operations",
            "Operation sequence is incomplete.",
        ));
    }

    let models: Vec<&ModelOperation> = operations
        .iter()
        .filter_map(AgentOperation::as_model)
        .collect();
    let tools: Vec<&ToolOperation> = operations
        .iter()
        .filter_map(AgentOperation::as_tool)
        .collect();
    let mut model_ordinals: Vec<i64> = models.iter().map(|operation| operation.ordinal).collect();
    model_ordinals.sort_unstable();
    if !is_one_through(&model_ordinals, summary.counts.model_requests) {
        diagnostics.push(diagnostic(
            "model_ordinal_noncontiguous",
            "operations",
            "Model-request ordinals are not contiguous.",
        ));
    }
    if raw_operations.len() as i64 != summary.counts.operations {
        diagnostics.push(diagnostic(
            "operation_count_mismatch",
            "operations",
            "Owner operation count is inconsistent.",
        ));
    }
    if model_ordinals.len() as i64 != summary.counts.model_requests {
        diagnostics.push(diagnostic(
            "model_count_mismatch",
            "operations",
            "Owner model count is inconsistent.",
        ));
    }

    let tool_counts = summary.counts.tool_calls;
    if !tool_counts.is_monotonic() {
        diagnostics.push(diagnostic(
            "tool_count_inequality",
            "counts.tool_calls",
            "Tool counts are inconsistent.",
        ));
    }
    if tool_counts.admitted > summary.limits.tool_calls {
        diagnostics.push(diagnostic(
            "tool_limit_mismatch",
            "counts.tool_calls",
            "Admitted Tool count exceeds limit.",
        ));
    }

    // A Tool-calls response that is not inspectable hides how many calls it
    // requested, so requested-call reconciliation cannot be judged.
    let opaque_tool_call_response = models.iter().any(|operation| {
        operation.response_type == Some(ResponseType::ToolCalls)
            && operation
                .response
                .as_ref()
                .is_some_and(|response| response.mode != PayloadMode::Full)
    });
    if opaque_tool_call_response {
        return;
    }
    let requested: Vec<(&str, i64)> = models
        .iter()
        .flat_map(|operation| &operation.requested_tool_calls)
        .map(|call| (call.call_id.as_str(), call.ordinal))
        .collect();
    if requested.len() as i64 != tool_counts.requested {
        diagnostics.push(diagnostic(
            "tool_call_identity_mismatch",
            "operations.requested_tool_calls",
            "Requested Tool-call count does not reconcile.",
        ));
    }
    if has_duplicates(requested.iter()) {
        diagnostics.push(diagnostic(
            "tool_call_identity_mismatch",
            "operations.requested_tool_calls",
            "Requested Tool-call identity duplicates.",
        ));
    }
    let requested: HashSet<(&str, i64)> = requested.into_iter().collect();
    if !tools
        .iter()
        .all(|operation| requested.contains(&(operation.call_id.as_str(), operation.ordinal)))
    {
        diagnostics.push(diagnostic(
            "tool_call_identity_mismatch",
            "operations.tool",
            "Tool operation does not match a requested call.",
        ));
    }
}

fn validate_operation_correspondence(
    summary: &AgentExecutionSummary,
    operations: &[AgentOperation],
    definition: Option<&AgentDefinitionContext>,
    admitted_call_ids: AdmittedCallIds<'_>,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) {
    let models: Vec<&ModelOperation> = operations
        .iter()
        .filter_map(AgentOperation::as_model)
        .collect();
    let tools: Vec<&ToolOperation> = operations
        .iter()
        .filter_map(AgentOperation::as_tool)
        .collect();

    // Every call an inspectable Tool-calls response requested, by identity.
    let mut requested: HashMap<(&str, i64), &JsonObject> = HashMap::new();
    let mut next_ordinal = 1;
    for operation in &models {
        let calls = operation
            .response
            .as_ref()
            .filter(|response| response.mode == PayloadMode::Full)
            .and_then(|response| response.value.as_object())
            .filter(|value| get(value, "type").as_str() == Some("tool_calls"))
            .and_then(|value| get(value, "calls").as_array());
        for call in calls.into_iter().flatten() {
            if let Some(call) = call.as_object()
                && let Some(call_id) = get(call, "id").as_str()
            {
                requested.insert((call_id, next_ordinal), call);
            }
            next_ordinal += 1;
        }
    }

    if has_duplicates(
        tools
            .iter()
            .map(|operation| (&operation.call_id, operation.ordinal)),
    ) {
        diagnostics.push(diagnostic(
            "tool_call_identity_mismatch",
            "operations.tool",
            "More than one Tool operation owns the same requested call.",
        ));
    }
    for operation in &tools {
        let mut mismatch = false;
        if let Some(call) = requested.get(&(operation.call_id.as_str(), operation.ordinal)) {
            mismatch = get(call, "name").as_str() != Some(operation.tool_name.as_str());
            if operation.requested_arguments.mode == PayloadMode::Full {
                mismatch = mismatch
                    || !values_equal(&operation.requested_arguments.value, get(call, "arguments"));
            }
        }
        if let Some(definition) = definition {
            mismatch = mismatch
                || definition.tool_structural_ids.get(&operation.tool_name)
                    != Some(&operation.tool_structural_id);
        }
        if mismatch {
            diagnostics.push(diagnostic(
                "tool_operation_correspondence_mismatch",
                format!("operations[{}]", operation.sequence),
                "Tool operation does not match the requested call and declared Tool.",
            ));
        }
    }

    let expected_admitted =
        admitted_call_ids.map_or(summary.counts.tool_calls.admitted, |ids| ids.len() as i64);
    let expected_started = tools
        .iter()
        .filter(|operation| {
            operation.arguments.is_some()
                && (operation.result_candidate.available
                    || operation.result_candidate.unavailable_reason
                        != Some(UnavailableReason::NotInvoked))
        })
        .count() as i64;
    let expected_completed = tools
        .iter()
        .filter(|operation| operation.result.is_some())
        .count() as i64;
    let observed = summary.counts.tool_calls;
    if (expected_admitted, expected_started, expected_completed)
        != (observed.admitted, observed.started, observed.completed)
    {
        diagnostics.push(diagnostic(
            "tool_count_reconciliation_mismatch",
            "counts.tool_calls",
            "Owner Tool counts do not match realized Tool operation evidence.",
        ));
    }

    let mut expected_usage = AgentUsage {
        model_responses: 0,
        fields: BTreeMap::new(),
    };
    for operation in models
        .iter()
        .filter(|operation| operation.response.is_some())
    {
        expected_usage.model_responses += 1;
        for (field, value) in operation.usage.iter().flat_map(|usage| usage.reported()) {
            let aggregate = expected_usage
                .fields
                .entry(field)
                .or_insert(UsageAggregate {
                    sum: 0,
                    observations: 0,
                });
            aggregate.sum += value;
            aggregate.observations += 1;
        }
    }
    if summary.usage != expected_usage {
        diagnostics.push(diagnostic(
            "agent_usage_mismatch",
            "junjo.agent.usage",
            "Owner usage does not match validated model response evidence.",
        ));
    }
}

/// The Tool call identities the replayed Store admitted. Only a verified
/// replay with an inspectable end state can answer.
fn replayed_admitted_call_ids(
    store_result: &StoreReconstructionResult,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<HashSet<String>> {
    if !store_result.replay_verified {
        return None;
    }
    let end = store_result
        .detail
        .end
        .as_ref()
        .filter(|end| end.mode == PayloadMode::Full)?
        .value
        .as_object()?;
    let ids: Option<Vec<&str>> = get(end, "admitted_tool_call_ids")
        .as_array()
        .and_then(|ids| ids.iter().map(nonempty_text).collect());
    match ids {
        Some(ids) if !has_duplicates(ids.iter()) => {
            Some(ids.into_iter().map(str::to_string).collect())
        }
        _ => {
            diagnostics.push(diagnostic(
                "invalid_admission_evidence",
                "junjo.agent.state.end.admitted_tool_call_ids",
                "Replayed Tool admission identities are invalid.",
            ));
            None
        }
    }
}

fn span_identity(span: &JsonObject) -> Option<(&str, &str)> {
    Some((
        lower_hex(get(span, "trace_id"), 32)?,
        lower_hex(get(span, "span_id"), 16)?,
    ))
}

/// Reject matching Agent Store events attached outside causal owner scopes.
fn diagnose_out_of_scope_store_events(
    trace_spans: &[&JsonObject],
    eligible_spans: &[&JsonObject],
    store_id: &Json,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) {
    let Some(store_id) = nonempty_text(store_id) else {
        return;
    };
    let eligible: HashSet<(&str, &str)> = eligible_spans
        .iter()
        .filter_map(|span| span_identity(span))
        .collect();
    for (index, span) in trace_spans.iter().enumerate() {
        if span_identity(span).is_some_and(|identity| eligible.contains(&identity)) {
            continue;
        }
        if owned_store_events(span, store_id).next().is_some() {
            diagnostics.push(diagnostic(
                "store_causal_owner_mismatch",
                span_evidence_path(span, "events_json", Some(index)),
                "Agent Store transition is attached outside its owner or operation spans.",
            ));
        }
    }
}

/// Each Store action belongs on one kind of span, and each operation's
/// revisions must match the transitions it caused.
fn validate_agent_store_causality(
    owner_span: &JsonObject,
    operations: &[&JsonObject],
    store_id: &Json,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) {
    const ACTION: &str = "junjo.store.action";
    const REVISION_BEFORE: &str = "junjo.store.revision.before";
    const REVISION_AFTER: &str = "junjo.store.revision.after";
    let Some(store_id) = nonempty_text(store_id) else {
        return;
    };
    for span in std::iter::once(&owner_span).chain(operations) {
        let attributes = attributes(span);
        let operation_type = get(attributes, OPERATION_TYPE).as_str();
        let allowed: &[&str] = if std::ptr::eq(*span, owner_span) {
            &["admit_tool_batch", "commit_success", "set_terminal_reason"]
        } else {
            match operation_type {
                Some("model_request") => &["record_model_start", "record_model_response"],
                Some("tool") => &["record_tool_started", "record_tool_result"],
                _ => &[],
            }
        };
        let events: Vec<&JsonObject> = owned_store_events(span, store_id).collect();
        for event in &events {
            if portable_enum(get(event, ACTION), allowed).is_none() {
                diagnostics.push(diagnostic(
                    "store_causal_owner_mismatch",
                    span_evidence_path(span, ACTION, None),
                    "Store transition action is attached to the wrong causal span.",
                ));
            }
        }
        let with_action = |action: &str| -> Vec<&JsonObject> {
            events
                .iter()
                .copied()
                .filter(|event| get(event, ACTION).as_str() == Some(action))
                .collect()
        };
        // Exactly one transition, whose revision equals the operation's.
        let single_matches = |events: &[&JsonObject], revision_key: &str, expected: &Json| matches!(events, [event] if values_equal(get(event, revision_key), expected));
        let span_path = || span_evidence_path(span, "", None);

        match operation_type {
            Some("model_request") => {
                let expected = get(attributes, "junjo.agent.model_request.state_revision");
                if !single_matches(&with_action("record_model_start"), REVISION_AFTER, expected) {
                    diagnostics.push(diagnostic(
                        "model_state_revision_mismatch",
                        span_path(),
                        "Model request revision does not match its causal Store transition.",
                    ));
                }
                let responses = with_action("record_model_response");
                let response_expected =
                    payload_slot_present(attributes, "junjo.agent.model.response");
                if responses.len() != usize::from(response_expected) {
                    diagnostics.push(diagnostic(
                        "model_response_causality_mismatch",
                        span_path(),
                        "Model response evidence does not match its causal Store transition.",
                    ));
                }
            }
            Some("tool") => {
                let started = with_action("record_tool_started");
                let results = with_action("record_tool_result");
                let before = get(attributes, "junjo.agent.tool.state_revision.before");
                let after = get(attributes, "junjo.agent.tool.state_revision.after");
                let started_expected = is_true(get(
                    attributes,
                    "junjo.agent.tool.result_candidate.available",
                )) || get(
                    attributes,
                    "junjo.agent.tool.result_candidate.unavailable_reason",
                )
                .as_str()
                    != Some("not_invoked");
                let start_matches = if started_expected {
                    single_matches(&started, REVISION_BEFORE, before)
                } else {
                    started.is_empty()
                };
                if !start_matches {
                    diagnostics.push(diagnostic(
                        "tool_state_revision_mismatch",
                        span_path(),
                        "Tool start revision does not match its causal Store transition.",
                    ));
                }
                let result_expected =
                    !after.is_null() || payload_slot_present(attributes, "junjo.agent.tool.result");
                let result_matches = if result_expected {
                    single_matches(&results, REVISION_AFTER, after)
                } else {
                    results.is_empty()
                };
                if !result_matches {
                    diagnostics.push(diagnostic(
                        "tool_state_revision_mismatch",
                        span_path(),
                        "Tool result revision does not match its causal Store transition.",
                    ));
                }
            }
            _ => {}
        }
    }
}

/// The owner's facts and the Store's own record of them must agree.
fn validate_state_correspondence(
    summary: &AgentExecutionSummary,
    state: &StoreDetail,
    input_evidence: Option<&PayloadEvidence>,
    output_evidence: Option<&PayloadEvidence>,
    operations: &[AgentOperation],
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) {
    fn inspectable(evidence: Option<&PayloadEvidence>) -> Option<&PayloadEvidence> {
        evidence.filter(|evidence| evidence.mode == PayloadMode::Full)
    }
    if let Some(start) = inspectable(state.start.as_ref()).and_then(|start| start.value.as_object())
        && let Some(input) = inspectable(input_evidence)
        && !values_equal(get(start, "input"), &input.value)
    {
        diagnostics.push(diagnostic(
            "state_owner_mismatch",
            "junjo.agent.state.start.input",
            "Store start input does not match owner input evidence.",
        ));
    }

    let Some(end) = inspectable(state.end.as_ref()).and_then(|end| end.value.as_object()) else {
        return;
    };
    let counts = summary.counts;
    let termination = serde_json::to_value(summary.termination_reason).unwrap_or_default();
    let expected = [
        ("model_request_count", json!(counts.model_requests)),
        (
            "tool_call_requested_count",
            json!(counts.tool_calls.requested),
        ),
        (
            "tool_call_admitted_count",
            json!(counts.tool_calls.admitted),
        ),
        ("tool_call_started_count", json!(counts.tool_calls.started)),
        (
            "tool_call_completed_count",
            json!(counts.tool_calls.completed),
        ),
        ("usage", agent_usage_contract_value(&summary.usage)),
        ("terminal_reason", termination),
    ];
    if expected
        .iter()
        .any(|(key, value)| !values_equal(get(end, key), value))
    {
        diagnostics.push(diagnostic(
            "state_owner_mismatch",
            "junjo.agent.state.end",
            "Store terminal counters, usage, or reason do not match owner evidence.",
        ));
    }

    let final_available = get(end, "final_output_available");
    let final_output = get(end, "final_output");
    if summary.outcome != Outcome::Completed {
        if final_available != &Json::Bool(false) || !final_output.is_null() {
            diagnostics.push(diagnostic(
                "final_output_mismatch",
                "junjo.agent.state.end.final_output",
                "Non-completed Agent Store cannot contain committed final output.",
            ));
        }
        return;
    }
    match output_evidence {
        Some(output) if is_true(final_available) => {
            if output.mode == PayloadMode::Full && !values_equal(final_output, &output.value) {
                diagnostics.push(diagnostic(
                    "final_output_mismatch",
                    "junjo.agent.output",
                    "Inspectable owner output does not match the committed Store output.",
                ));
            }
        }
        _ => diagnostics.push(diagnostic(
            "final_output_mismatch",
            "junjo.agent.output",
            "Completed Agent requires owner output and committed Store output evidence.",
        )),
    }
    let final_responses = operations
        .iter()
        .filter_map(AgentOperation::as_model)
        .filter(|operation| {
            operation.response_type == Some(ResponseType::FinalOutput)
                && operation.response.is_some()
        })
        .count();
    if final_responses != 1 {
        diagnostics.push(diagnostic(
            "final_output_mismatch",
            "operations.model.response.output",
            "Completed Agent requires exactly one normalized final model response.",
        ));
    }
}

/// The name an executable is known by: an Agent's declared name, or the span
/// name of anything else.
fn executable_name<'a>(span: &'a JsonObject, executable_type: &str) -> &'a Json {
    if executable_type == "agent" {
        get(attributes(span), "junjo.agent.name")
    } else {
        get(span, "name")
    }
}

/// Project only executable spans directly parented by an owned Tool
/// operation.
fn nested_executables(
    owner_span: &JsonObject,
    spans: &[&JsonObject],
    eligible_operations: &[&JsonObject],
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Vec<NestedExecutableReference> {
    let mut tool_parents: HashMap<&str, i64> = HashMap::new();
    for operation in eligible_operations {
        let attributes = attributes(operation);
        if get(attributes, OPERATION_TYPE).as_str() != Some("tool") {
            continue;
        }
        if let Some(span_id) = get(operation, "span_id").as_str()
            && let Some(sequence) = contract_int(get(attributes, OPERATION_SEQUENCE), 1)
        {
            tool_parents.insert(span_id, sequence);
        }
    }

    let owner_trace_id = get(owner_span, "trace_id");
    let owner_attributes = attributes(owner_span);
    let expected_parent = [
        ("junjo.parent_executable_type", &json!("agent")),
        (
            "junjo.parent_executable_definition_id",
            get(owner_attributes, "junjo.executable_definition_id"),
        ),
        (
            "junjo.parent_executable_runtime_id",
            get(owner_attributes, "junjo.executable_runtime_id"),
        ),
        (
            "junjo.parent_executable_structural_id",
            get(owner_attributes, "junjo.executable_structural_id"),
        ),
    ];
    let mut nested = Vec::new();
    for span in spans {
        let attributes = attributes(span);
        let raw_type = get(attributes, "junjo.span_type");
        let parent = nonempty_text(get(span, "parent_span_id"))
            .and_then(|parent_span_id| tool_parents.get_key_value(parent_span_id));
        let Some((parent_span_id, parent_sequence)) = parent else {
            continue;
        };
        let Some(executable_type) = portable_enum(raw_type, &["workflow", "agent"]) else {
            // Other span types are not nested executables. A type that is
            // not even text is malformed evidence.
            if !raw_type.is_null() && nonempty_text(raw_type).is_none() {
                diagnostics.push(diagnostic(
                    "invalid_nested_executable",
                    span_evidence_path(span, "junjo.span_type", None),
                    "Nested executable type is invalid.",
                ));
            }
            continue;
        };
        if !require_active_contract(attributes, diagnostics) {
            continue;
        }
        if !values_equal(get(span, "trace_id"), owner_trace_id) {
            diagnostics.push(diagnostic(
                "invalid_nested_executable_parent",
                span_evidence_path(span, "trace_id", None),
                "Nested executable is not in its parent Agent trace.",
            ));
            continue;
        }
        if expected_parent
            .iter()
            .any(|(key, value)| !values_equal(get(attributes, key), value))
        {
            diagnostics.push(diagnostic(
                "nested_parent_correspondence_mismatch",
                span_evidence_path(span, "parent_executable", None),
                "Nested executable semantic parent does not match the owning Agent.",
            ));
            continue;
        }
        let identity = (
            nonempty_text(get(span, "trace_id")),
            nonempty_text(get(span, "span_id")),
            nonempty_text(get(attributes, "junjo.executable_definition_id")),
            nonempty_text(get(attributes, "junjo.executable_runtime_id")),
            nonempty_text(get(attributes, "junjo.executable_structural_id")),
            nonempty_text(executable_name(span, executable_type)),
        );
        let (
            Some(trace_id),
            Some(span_id),
            Some(definition_id),
            Some(runtime_id),
            Some(structural_id),
            Some(name),
        ) = identity
        else {
            diagnostics.push(diagnostic(
                "invalid_nested_executable",
                span_evidence_path(span, "", None),
                "Nested executable identity contains a missing or non-string value.",
            ));
            continue;
        };
        let reference = nested_reference_is_representable(
            executable_type,
            parent_span_id,
            trace_id,
            span_id,
            structural_id,
        )
        .map_err(str::to_string)
        .and_then(|()| service_identity(span).map_err(|error| error.message));
        match reference {
            Ok(service) => nested.push(NestedExecutableReference {
                executable_type: if executable_type == "agent" {
                    NestedExecutableType::Agent
                } else {
                    NestedExecutableType::Workflow
                },
                parent_operation_sequence: *parent_sequence,
                parent_operation_span_id: parent_span_id.to_string(),
                trace_id: trace_id.to_string(),
                span_id: span_id.to_string(),
                service,
                definition_id: definition_id.to_string(),
                runtime_id: runtime_id.to_string(),
                structural_id: structural_id.to_string(),
                name: name.to_string(),
            }),
            Err(reason) => diagnostics.push(diagnostic(
                "invalid_nested_executable",
                span_evidence_path(span, "", None),
                reason,
            )),
        }
    }
    nested.sort_by(|left, right| {
        (
            left.parent_operation_sequence,
            &left.parent_operation_span_id,
            &left.span_id,
        )
            .cmp(&(
                right.parent_operation_sequence,
                &right.parent_operation_span_id,
                &right.span_id,
            ))
    });
    nested
}

fn nested_reference_is_representable(
    executable_type: &str,
    parent_operation_span_id: &str,
    trace_id: &str,
    span_id: &str,
    structural_id: &str,
) -> Result<(), &'static str> {
    if !is_lower_hex(parent_operation_span_id, 16)
        || !is_lower_hex(trace_id, 32)
        || !is_lower_hex(span_id, 16)
    {
        return Err("Nested executable identities must be exact lowercase hexadecimal text.");
    }
    if executable_type == "agent" && !is_structural_id(structural_id, "agent_sha256:") {
        return Err("Nested Agent structural ID is invalid.");
    }
    Ok(())
}

/// Resolve the executable that semantically owns this Agent, if any.
fn parent_executable(
    owner_span: &JsonObject,
    spans: &[&JsonObject],
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<ParentExecutableReference> {
    const DECLARED_TYPE: &str = "junjo.parent_executable_type";
    const DECLARED_DEFINITION: &str = "junjo.parent_executable_definition_id";
    const DECLARED_RUNTIME: &str = "junjo.parent_executable_runtime_id";
    const DECLARED_STRUCTURAL: &str = "junjo.parent_executable_structural_id";
    let semantic_keys = [
        DECLARED_TYPE,
        DECLARED_DEFINITION,
        DECLARED_RUNTIME,
        DECLARED_STRUCTURAL,
    ];
    fn mismatch(
        diagnostics: &mut Vec<EvidenceDiagnostic>,
        message: &str,
    ) -> Option<ParentExecutableReference> {
        diagnostics.push(diagnostic(
            "parent_executable_correspondence_mismatch",
            "owner.parent_executable",
            message,
        ));
        None
    }
    let owner_attributes = attributes(owner_span);
    let raw_parent_span_id = get(owner_span, "parent_span_id");
    if raw_parent_span_id.is_null() {
        if semantic_keys
            .iter()
            .any(|key| owner_attributes.contains_key(*key))
        {
            return mismatch(
                diagnostics,
                "Root Agent cannot declare a semantic parent executable.",
            );
        }
        return None;
    }
    let Some(parent_span_id) = lower_hex(raw_parent_span_id, 16) else {
        diagnostics.push(diagnostic(
            "invalid_parent_executable",
            "owner.parent_span_id",
            "Physical parent span identity is invalid.",
        ));
        return None;
    };
    let owner_trace_id = get(owner_span, "trace_id");
    let in_owner_trace = |span: &JsonObject| values_equal(get(span, "trace_id"), owner_trace_id);
    let physical_matches: Vec<&JsonObject> = spans
        .iter()
        .copied()
        .filter(|span| {
            in_owner_trace(span) && get(span, "span_id").as_str() == Some(parent_span_id)
        })
        .collect();

    if semantic_keys
        .iter()
        .all(|key| get(owner_attributes, key).is_null())
    {
        // Nothing is declared. That is only valid under a span that is not a
        // Junjo execution span.
        let physical_attributes = physical_matches.first().map(|span| attributes(span));
        let under_junjo_execution = physical_attributes.is_some_and(|physical| {
            portable_enum(get(physical, "junjo.span_type"), &ExecutableType::NAMES).is_some()
                || physical.contains_key(OPERATION_TYPE)
        });
        if under_junjo_execution {
            return mismatch(
                diagnostics,
                "Agent under a Junjo execution span must declare its semantic parent.",
            );
        }
        return None;
    }
    let [physical_parent] = physical_matches[..] else {
        diagnostics.push(diagnostic(
            "parent_executable_missing",
            "owner.parent_span_id",
            "Physical parent span evidence is absent or ambiguous.",
        ));
        return None;
    };
    let declared = (
        portable_enum(get(owner_attributes, DECLARED_TYPE), &ExecutableType::NAMES),
        nonempty_text(get(owner_attributes, DECLARED_DEFINITION)),
        nonempty_text(get(owner_attributes, DECLARED_RUNTIME)),
        nonempty_text(get(owner_attributes, DECLARED_STRUCTURAL)),
    );
    let (Some(declared_type), Some(definition_id), Some(runtime_id), Some(structural_id)) =
        declared
    else {
        return mismatch(
            diagnostics,
            "Semantic parent executable identity is absent or incomplete.",
        );
    };
    let semantic_matches: Vec<&JsonObject> = spans
        .iter()
        .copied()
        .filter(|span| {
            let attributes = attributes(span);
            in_owner_trace(span)
                && get(attributes, "junjo.span_type").as_str() == Some(declared_type)
                && get(attributes, "junjo.executable_definition_id").as_str() == Some(definition_id)
                && get(attributes, "junjo.executable_runtime_id").as_str() == Some(runtime_id)
                && get(attributes, "junjo.executable_structural_id").as_str() == Some(structural_id)
        })
        .collect();
    let [parent] = semantic_matches[..] else {
        return mismatch(
            diagnostics,
            "Declared semantic parent does not resolve uniquely in the trace.",
        );
    };
    let parent_attributes = attributes(parent);
    if !require_active_contract(parent_attributes, diagnostics) {
        return None;
    }
    let physical_attributes = attributes(physical_parent);
    let physical_operation_type = get(physical_attributes, OPERATION_TYPE);
    if physical_operation_type.is_null() {
        if !values_equal(get(physical_parent, "span_id"), get(parent, "span_id")) {
            diagnostics.push(diagnostic(
                "parent_executable_correspondence_mismatch",
                "owner.parent_span_id",
                "Physical parent must be the declared semantic parent unless an owned Tool operation intervenes.",
            ));
            return None;
        }
    } else {
        // The only span allowed between an Agent and its semantic parent is
        // a Tool operation that the parent Agent owns.
        let owned_tool = declared_type == "agent"
            && physical_operation_type.as_str() == Some("tool")
            && require_active_contract(physical_attributes, diagnostics)
            && values_equal(
                get(physical_parent, "parent_span_id"),
                get(parent, "span_id"),
            )
            && values_equal(
                get(physical_attributes, "junjo.agent.runtime_id"),
                get(parent_attributes, "junjo.executable_runtime_id"),
            )
            && values_equal(
                get(physical_attributes, "junjo.agent.key"),
                get(parent_attributes, "junjo.agent.key"),
            );
        if !owned_tool {
            diagnostics.push(diagnostic(
                "parent_executable_correspondence_mismatch",
                "owner.parent_span_id",
                "Physical Tool parent is not owned by the declared semantic Agent parent.",
            ));
            return None;
        }
    }

    let reference = (|| {
        let executable_type = ExecutableType::from_name(declared_type)
            .ok_or("Parent executable type is invalid.".to_string())?;
        let trace_id = lower_hex(get(parent, "trace_id"), 32)
            .ok_or("Parent trace identity must be exact lowercase hexadecimal text.".to_string())?;
        let span_id = lower_hex(get(parent, "span_id"), 16)
            .ok_or("Parent span identity must be exact lowercase hexadecimal text.".to_string())?;
        let name = nonempty_text(executable_name(parent, declared_type))
            .ok_or("Parent executable name is absent or invalid.".to_string())?;
        Ok(ParentExecutableReference {
            executable_type,
            trace_id: trace_id.to_string(),
            physical_parent_span_id: parent_span_id.to_string(),
            span_id: span_id.to_string(),
            service: service_identity(parent).map_err(|error| error.message)?,
            definition_id: definition_id.to_string(),
            runtime_id: runtime_id.to_string(),
            structural_id: structural_id.to_string(),
            name: name.to_string(),
        })
    })();
    match reference {
        Ok(reference) => Some(reference),
        Err(reason) => {
            let reason: String = reason;
            diagnostics.push(diagnostic(
                "invalid_parent_executable",
                "owner.parent_span_id",
                reason,
            ));
            None
        }
    }
}

/// Assemble one owner-scoped semantic detail from a complete trace.
///
/// The owner may come from a separate query. Its operations and its private
/// runtime Store events are matched to it by transport identity, never by
/// being the same object. Its application Store carriers are selected as
/// `store_evidence_spans` describes.
///
/// `store_index` is the index of `trace_spans` when the caller has already
/// built it. Without one, it is built here.
pub fn assemble_agent_detail(
    owner_span: &JsonObject,
    trace_spans: &[&JsonObject],
    store_index: Option<&StoreSpanIndex<'_>>,
) -> Result<AgentExecutionDetail, AgentEvidenceError> {
    let summary = assemble_agent_summary(owner_span)?;
    let attributes = attributes(owner_span);
    let mut diagnostics = Vec::new();
    if attributes
        .keys()
        .any(|key| key.starts_with("junjo.graph") || key.starts_with("junjo.workflow"))
    {
        diagnostics.push(diagnostic(
            "agent_graph_evidence_forbidden",
            "owner.attributes",
            "Agent owns no Graph evidence.",
        ));
    }
    let definition = parse_required_payload_slot(
        attributes,
        "junjo.agent.definition_snapshot",
        &mut diagnostics,
    );
    let definition_context =
        validate_definition_snapshot(&definition, attributes, &mut diagnostics);

    // Every span that claims to be an operation of this execution. Only
    // those that also prove ownership become eligible.
    let raw_operations: Vec<&JsonObject> = trace_spans
        .iter()
        .copied()
        .filter(|span| {
            let attributes = crate::spans::attributes(span);
            get(attributes, "junjo.agent.runtime_id").as_str() == Some(summary.runtime_id.as_str())
                && attributes.contains_key(OPERATION_TYPE)
        })
        .collect();
    let mut eligible_operations: Vec<&JsonObject> = Vec::new();
    for span in &raw_operations {
        let operation_attributes = crate::spans::attributes(span);
        let contract_supported = require_active_contract(operation_attributes, &mut diagnostics);
        let checks = [
            (
                get(span, "trace_id").as_str() == Some(summary.trace_id.as_str()),
                "trace_id",
                "Operation trace identity does not match its Agent owner.",
            ),
            (
                get(operation_attributes, "junjo.agent.key").as_str()
                    == Some(summary.agent_key.as_str()),
                "junjo.agent.key",
                "Operation Agent key does not match its owner.",
            ),
            (
                get(span, "parent_span_id").as_str() == Some(summary.agent_span_id.as_str()),
                "parent_span_id",
                "Operation is not a direct child of its Agent owner.",
            ),
        ];
        let mut owner_matches = true;
        for (matches, suffix, message) in checks {
            if !matches {
                diagnostics.push(diagnostic(
                    "operation_owner_mismatch",
                    span_evidence_path(span, suffix, None),
                    message,
                ));
                owner_matches = false;
            }
        }
        if contract_supported && owner_matches {
            eligible_operations.push(span);
        }
    }
    let tool_spans: Vec<&JsonObject> = eligible_operations
        .iter()
        .copied()
        .filter(|span| get(crate::spans::attributes(span), OPERATION_TYPE).as_str() == Some("tool"))
        .collect();
    let owned_spans: Vec<&JsonObject> = std::iter::once(owner_span)
        .chain(eligible_operations.iter().copied())
        .collect();
    let store_id = get(attributes, "junjo.agent.store.id");
    diagnose_out_of_scope_store_events(trace_spans, &owned_spans, store_id, &mut diagnostics);
    validate_agent_store_causality(owner_span, &eligible_operations, store_id, &mut diagnostics);
    let mut store_result = reconstruct_store(attributes, &owned_spans, &AGENT_STORE_BOUNDARY);
    diagnostics.append(&mut store_result.diagnostics);
    let built_index;
    let store_index = match store_index {
        Some(index) => index,
        None => {
            built_index = index_store_spans(trace_spans);
            &built_index
        }
    };
    let (application_spans, application_issues) = store_evidence_spans(
        owner_span,
        get(
            attributes,
            AGENT_APPLICATION_STORE_BOUNDARY.store_id_attribute,
        ),
        store_index,
    );
    let mut application_result = reconstruct_store(
        attributes,
        &application_spans,
        &AGENT_APPLICATION_STORE_BOUNDARY,
    );
    diagnostics.extend(application_issues);
    diagnostics.append(&mut application_result.diagnostics);
    if summary.termination_reason == TerminationReason::InternalError
        && get(attributes, "error.type").as_str() == Some("AgentInternalError")
        && is_true(get(attributes, "junjo.agent.state.available"))
        && !store_result.detail.reconstructable_claimed
    {
        diagnostics.push(diagnostic(
            "terminal_store_commit_failed",
            "junjo.store.reconstructable",
            "Terminal Store transaction failed; recovered evidence is intentionally partial.",
        ));
    }
    let admitted_call_ids = replayed_admitted_call_ids(&store_result, &mut diagnostics);

    let context = OperationContext {
        tool_spans: &tool_spans,
        admitted_call_ids: admitted_call_ids.as_ref(),
        owner_termination: summary.termination_reason,
        definition: definition_context.as_ref(),
    };
    let mut ordered_operations = eligible_operations.clone();
    ordered_operations.sort_by_cached_key(|span| operation_sort_key(span));
    let mut operations: Vec<AgentOperation> = Vec::new();
    let mut next_tool_ordinal = Some(1);
    for span in ordered_operations {
        match get(crate::spans::attributes(span), OPERATION_TYPE).as_str() {
            Some("model_request") => {
                let (operation, next) =
                    model_operation(span, &context, next_tool_ordinal, &mut diagnostics);
                next_tool_ordinal = next;
                operations.extend(operation.map(AgentOperation::Model));
            }
            Some("tool") => {
                let operation = tool_operation(span, context.admitted_call_ids, &mut diagnostics);
                operations.extend(operation.map(AgentOperation::Tool));
            }
            _ => diagnostics.push(diagnostic(
                "invalid_operation_type",
                span_evidence_path(span, "", None),
                "Agent operation type is unsupported.",
            )),
        }
    }
    operations.sort_by(|left, right| {
        (left.sequence(), left.span_id()).cmp(&(right.sequence(), right.span_id()))
    });
    validate_sequences_and_counts(&summary, &raw_operations, &operations, &mut diagnostics);
    validate_operation_correspondence(
        &summary,
        &operations,
        context.definition,
        context.admitted_call_ids,
        &mut diagnostics,
    );

    let state_available = get(attributes, "junjo.agent.state.available");
    let mut input = if is_true(state_available) {
        Some(parse_required_payload_slot(
            attributes,
            "junjo.agent.input",
            &mut diagnostics,
        ))
    } else {
        parse_payload_slot(attributes, "junjo.agent.input", &mut diagnostics)
    };
    if state_available == &Json::Bool(false) && input.is_some() {
        diagnostics.push(diagnostic(
            "unexpected_boundary_input_evidence",
            "junjo.agent.input",
            "State-unavailable Agent cannot carry validated input evidence.",
        ));
        input = None;
    }
    let mut output = if summary.outcome == Outcome::Completed {
        Some(parse_required_payload_slot(
            attributes,
            "junjo.agent.output",
            &mut diagnostics,
        ))
    } else {
        parse_payload_slot(attributes, "junjo.agent.output", &mut diagnostics)
    };
    if summary.outcome != Outcome::Completed && output.is_some() {
        diagnostics.push(diagnostic(
            "unexpected_output_evidence",
            "junjo.agent.output",
            "Non-completed Agent cannot publish validated output evidence.",
        ));
        output = None;
    }
    validate_state_correspondence(
        &summary,
        &store_result.detail,
        input.as_ref(),
        output.as_ref(),
        &operations,
        &mut diagnostics,
    );

    // A boundary rejection publishes the candidate it rejected, and only
    // that one.
    let mut candidate = |root: &str, expected: TerminationReason| {
        if summary.termination_reason == expected {
            return Some(parse_candidate(attributes, root, &mut diagnostics));
        }
        if candidate_present(attributes, root) {
            diagnostics.push(diagnostic(
                "unexpected_boundary_candidate_evidence",
                root,
                "Candidate evidence is forbidden for this termination reason.",
            ));
        }
        None
    };
    let input_candidate = candidate(
        "junjo.agent.input_candidate",
        TerminationReason::InputValidationError,
    );
    let history_candidate = candidate(
        "junjo.agent.history_candidate",
        TerminationReason::HistoryValidationError,
    );

    let parent_executable = parent_executable(owner_span, trace_spans, &mut diagnostics);
    let nested_executables = nested_executables(
        owner_span,
        trace_spans,
        &eligible_operations,
        &mut diagnostics,
    );
    let error = execution_error(owner_span, attributes, &mut diagnostics);
    // The summary already proved that a cancelled Agent carries its reason.
    let cancellation = cancellation_evidence(attributes, &mut diagnostics)
        .ok()
        .flatten();
    // Each span once, by span ID, in first-seen order. An application Store
    // carrier may also be the owner or one of its operations.
    let mut evidence_spans: IndexMap<&Json, &JsonObject> = IndexMap::new();
    for span in std::iter::once(owner_span)
        .chain(raw_operations.iter().copied())
        .chain(application_spans.iter().copied())
    {
        evidence_spans.insert(get(span, "span_id"), span);
    }
    let evidence_spans: Vec<&JsonObject> = evidence_spans.into_values().collect();
    let integrity = assemble_evidence_integrity(&evidence_spans, diagnostics);
    Ok(AgentExecutionDetail {
        summary,
        definition,
        input,
        output,
        input_candidate,
        history_candidate,
        operations,
        state: store_result.detail,
        application_state: application_result.detail,
        parent_executable,
        nested_executables,
        error,
        cancellation,
        integrity,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_tool_reason_identifies_only_the_undeclared_call_in_a_rejected_batch() {
        let definition = AgentDefinitionContext {
            agent_key: "agent".to_string(),
            instructions: String::new(),
            tools: Vec::new(),
            tool_structural_ids: HashMap::from([(
                "lookup".to_string(),
                format!("tool_sha256:{}", "0".repeat(64)),
            )]),
            output_schema: json!({}),
        };
        let response = json!({
            "type": "tool_calls",
            "calls": [
                {"id": "known-call", "name": "lookup", "arguments": {}},
                {"id": "unknown-call", "name": "missing", "arguments": {}},
            ],
        });
        let admitted = HashSet::new();
        let mut diagnostics = Vec::new();
        let (calls, next_ordinal) = requested_calls(
            Some(&response),
            &[],
            Some(&admitted),
            TerminationReason::UnknownTool,
            Some(1),
            Some(&definition),
            &mut diagnostics,
        );

        assert_eq!(next_ordinal, Some(3));
        let reasons: Vec<(&str, Option<RequestedToolCallReason>)> = calls
            .iter()
            .map(|call| (call.call_id.as_str(), call.reason))
            .collect();
        assert_eq!(
            reasons,
            [
                (
                    "known-call",
                    Some(RequestedToolCallReason::BatchPreflightRejected)
                ),
                ("unknown-call", Some(RequestedToolCallReason::UnknownTool)),
            ]
        );
        assert!(
            calls
                .iter()
                .all(|call| call.admission == Admission::NotAdmitted)
        );
        assert!(diagnostics.is_empty());
    }

    #[test]
    fn an_opaque_response_makes_later_tool_ordinals_unknown() {
        let mut diagnostics = Vec::new();
        let (calls, next_ordinal) = requested_calls(
            Some(&json!({"type": "tool_calls", "calls": [{"id": "a", "name": "b"}]})),
            &[],
            None,
            TerminationReason::FinalOutput,
            None,
            None,
            &mut diagnostics,
        );
        assert!(calls.is_empty());
        assert_eq!(next_ordinal, None);
    }

    #[test]
    fn sequences_one_through_n_are_recognized_without_building_the_range() {
        assert!(is_one_through(&[], 0));
        assert!(is_one_through(&[1, 2, 3], 3));
        assert!(!is_one_through(&[1, 2, 3], 4));
        assert!(!is_one_through(&[1, 3], 2));
        assert!(!is_one_through(&[2], 1));
        assert!(!is_one_through(&[], 9_007_199_254_740_991));
    }
}
