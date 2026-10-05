//! Strict telemetry-contract parsing helpers for Agent diagnostics.

use std::collections::{BTreeMap, HashMap, HashSet};

use serde_json::json;
use sha2::{Digest, Sha256};

use crate::agent_diagnostics::schemas::{
    AgentEvidenceError, AgentEvidenceErrorCode, AgentUsage, CancellationEvidence,
    CandidateEvidence, ExecutionError, ModelUsage, Outcome, ResponseType, UnavailableReason,
    UsageAggregate, UsageField,
};
use crate::json::{Json, JsonObject, display, get, member, values_equal};
use crate::store_diagnostics::payloads::{
    JsonDecodeError, decode_json_value, parse_required_payload_slot, payload_slot_present,
};
use crate::store_diagnostics::schemas::{EvidenceDiagnostic, PayloadEvidence, PayloadMode};
use crate::telemetry_contract::{
    ACTIVE_TELEMETRY_CONTRACT_VERSION, contract_int, is_active_contract_version, nonempty_text,
    span_evidence_path,
};
use crate::timestamps::{Timestamp, TimestampError};

/// Validated definition facts used to check normalized requests.
#[derive(Debug, Clone)]
pub struct AgentDefinitionContext {
    pub agent_key: String,
    pub instructions: String,
    /// Each Tool's descriptor without its structural fingerprint.
    pub tools: Vec<Json>,
    pub tool_structural_ids: HashMap<String, String>,
    pub output_schema: Json,
}

pub fn diagnostic(
    code: impl Into<String>,
    path: impl Into<String>,
    message: impl Into<String>,
) -> EvidenceDiagnostic {
    EvidenceDiagnostic::new(code, path, message)
}

/// Whether any candidate availability, reason, or payload member exists.
pub fn candidate_present(attributes: &JsonObject, root: &str) -> bool {
    payload_slot_present(attributes, root)
        || ["available", "unavailable_reason"]
            .iter()
            .any(|member| attributes.contains_key(&format!("{root}.{member}")))
}

pub fn required_int(
    attributes: &JsonObject,
    key: &str,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
    minimum: i64,
) -> Option<i64> {
    let value = contract_int(get(attributes, key), minimum);
    if value.is_none() {
        diagnostics.push(diagnostic(
            "invalid_contract_integer",
            key,
            format!("{key} is invalid."),
        ));
    }
    value
}

pub fn required_string<'a>(
    attributes: &'a JsonObject,
    key: &str,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<&'a str> {
    let value = nonempty_text(get(attributes, key));
    if value.is_none() {
        diagnostics.push(diagnostic(
            "required_identity_missing",
            key,
            format!("{key} is absent."),
        ));
    }
    value
}

/// Decode one attribute that carries contract JSON as text.
pub fn parse_json_attribute(
    attributes: &JsonObject,
    key: &str,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<Json> {
    let Some(raw) = get(attributes, key).as_str() else {
        diagnostics.push(diagnostic(
            "required_json_missing",
            key,
            format!("{key} is absent."),
        ));
        return None;
    };
    let (code, message) = match decode_json_value(raw) {
        Ok(value) => return Some(value),
        Err(JsonDecodeError::DuplicateName) => (
            "duplicate_json_object_name",
            format!("{key} repeats a JSON object name."),
        ),
        Err(JsonDecodeError::NonPortable) => (
            "nonportable_json_value",
            format!("{key} is outside the I-JSON interoperability domain."),
        ),
        Err(JsonDecodeError::TooDeep) => (
            "payload_nesting_too_deep",
            format!("{key} exceeds the contract payload nesting bound."),
        ),
        Err(JsonDecodeError::Invalid) => {
            ("invalid_json", format!("{key} is not valid finite JSON."))
        }
    };
    diagnostics.push(diagnostic(code, key, message));
    None
}

fn unsupported_contract(attributes: &JsonObject) -> Option<EvidenceDiagnostic> {
    let version = get(attributes, "junjo.telemetry.contract_version");
    (!is_active_contract_version(version)).then(|| {
        diagnostic(
            "unsupported_contract",
            "junjo.telemetry.contract_version",
            format!(
                "Expected telemetry contract {ACTIVE_TELEMETRY_CONTRACT_VERSION}; observed {}.",
                display(version)
            ),
        )
    })
}

/// The owner must declare the active contract, or nothing can be assembled.
pub fn require_owner_contract(attributes: &JsonObject) -> Result<(), AgentEvidenceError> {
    match unsupported_contract(attributes) {
        Some(issue) => Err(AgentEvidenceError {
            code: AgentEvidenceErrorCode::UnsupportedContract,
            message: issue.message.clone(),
            diagnostics: vec![issue],
        }),
        None => Ok(()),
    }
}

/// Whether a non-owner span declares the active contract. One that does not
/// is diagnosed and left out by the caller.
pub fn require_active_contract(
    attributes: &JsonObject,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> bool {
    match unsupported_contract(attributes) {
        Some(issue) => {
            diagnostics.push(issue);
            false
        }
        None => true,
    }
}

/// The reasons a producer may give for each unavailable candidate.
fn allowed_unavailable_reasons(root: &str) -> &'static [UnavailableReason] {
    use UnavailableReason::{
        Cancelled, NotInvoked, NotJsonSerializable, NotReturned, ServiceFailed,
    };
    match root {
        "junjo.agent.input_candidate" | "junjo.agent.history_candidate" => &[NotJsonSerializable],
        "junjo.agent.model.response_candidate" => &[NotReturned, Cancelled, NotJsonSerializable],
        "junjo.agent.tool.result_candidate" => {
            &[NotInvoked, ServiceFailed, Cancelled, NotJsonSerializable]
        }
        _ => &[],
    }
}

pub fn parse_candidate(
    attributes: &JsonObject,
    root: &str,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> CandidateEvidence {
    let reason_key = format!("{root}.unavailable_reason");
    match get(attributes, &format!("{root}.available")) {
        Json::Bool(true) => {
            if attributes.contains_key(&reason_key) {
                diagnostics.push(diagnostic(
                    "invalid_candidate_evidence",
                    reason_key,
                    "Available candidate cannot carry an unavailable reason.",
                ));
            }
            CandidateEvidence::available(parse_required_payload_slot(attributes, root, diagnostics))
        }
        Json::Bool(false) => {
            if payload_slot_present(attributes, root) {
                diagnostics.push(diagnostic(
                    "invalid_candidate_evidence",
                    root,
                    "Unavailable candidate cannot carry payload evidence.",
                ));
            }
            let reason = get(attributes, &reason_key)
                .as_str()
                .and_then(UnavailableReason::from_name)
                .filter(|reason| allowed_unavailable_reasons(root).contains(reason));
            if reason.is_none() {
                diagnostics.push(diagnostic(
                    "invalid_candidate_evidence",
                    reason_key,
                    "Unavailable candidate reason is invalid.",
                ));
            }
            CandidateEvidence::unavailable(
                reason.unwrap_or(UnavailableReason::ContractEvidenceMissing),
            )
        }
        _ => {
            diagnostics.push(diagnostic(
                "invalid_candidate_evidence",
                format!("{root}.available"),
                "Candidate availability is absent or invalid.",
            ));
            CandidateEvidence::unavailable(UnavailableReason::ContractEvidenceMissing)
        }
    }
}

/// Whether a usage payload declares version 1 as an integer.
fn is_version_one(value: &JsonObject) -> bool {
    contract_int(get(value, "v"), i64::MIN) == Some(1)
}

pub fn parse_agent_usage(
    attributes: &JsonObject,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<AgentUsage> {
    let root = "junjo.agent.usage";
    let invalid = |diagnostics: &mut Vec<EvidenceDiagnostic>, message: &str| {
        diagnostics.push(diagnostic("invalid_usage", root, message));
        None
    };
    let value = parse_json_attribute(attributes, root, diagnostics);
    let Some(value) = value
        .as_ref()
        .and_then(Json::as_object)
        .filter(|value| is_version_one(value))
    else {
        return invalid(diagnostics, "Agent usage shape is invalid.");
    };
    let (Some(model_responses), Some(fields)) = (
        contract_int(get(value, "modelResponses"), 0),
        get(value, "fields").as_object(),
    ) else {
        return invalid(diagnostics, "Agent usage counts are invalid.");
    };
    if fields
        .keys()
        .any(|name| UsageField::from_contract_name(name).is_none())
    {
        return invalid(diagnostics, "Agent usage field is unsupported.");
    }
    let mut parsed_fields = BTreeMap::new();
    for (name, aggregate) in fields {
        let Some(aggregate) = aggregate.as_object() else {
            return invalid(diagnostics, "Usage aggregate is invalid.");
        };
        let (Some(sum), Some(observations)) = (
            contract_int(get(aggregate, "sum"), 0),
            contract_int(get(aggregate, "observations"), 1),
        ) else {
            return invalid(diagnostics, "Usage aggregate counts are invalid.");
        };
        if let Some(field) = UsageField::from_contract_name(name) {
            parsed_fields.insert(field, UsageAggregate { sum, observations });
        }
    }
    Some(AgentUsage {
        model_responses,
        fields: parsed_fields,
    })
}

pub fn parse_model_usage(
    attributes: &JsonObject,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<ModelUsage> {
    let root = "junjo.agent.model.usage";
    if !attributes.contains_key(root) {
        return None;
    }
    let value = parse_json_attribute(attributes, root, diagnostics);
    let shape = value.as_ref().and_then(Json::as_object).filter(|value| {
        is_version_one(value)
            && value
                .keys()
                .all(|name| name == "v" || UsageField::from_contract_name(name).is_some())
    });
    let Some(value) = shape else {
        diagnostics.push(diagnostic(
            "invalid_usage",
            root,
            "Model usage shape is invalid.",
        ));
        return None;
    };
    let mut usage = ModelUsage::default();
    for (name, item) in value {
        let Some(field) = UsageField::from_contract_name(name) else {
            continue;
        };
        let Some(count) = contract_int(item, 0) else {
            diagnostics.push(diagnostic(
                "invalid_usage",
                root,
                "Model usage count is invalid.",
            ));
            return None;
        };
        *model_usage_field(&mut usage, field) = Some(count);
    }
    Some(usage)
}

fn model_usage_field(usage: &mut ModelUsage, field: UsageField) -> &mut Option<i64> {
    match field {
        UsageField::InputTokens => &mut usage.input_tokens,
        UsageField::OutputTokens => &mut usage.output_tokens,
        UsageField::CachedInputTokens => &mut usage.cached_input_tokens,
        UsageField::ReasoningTokens => &mut usage.reasoning_tokens,
        UsageField::TotalTokens => &mut usage.total_tokens,
    }
}

/// The usage payload a model response would carry for these counts.
pub fn model_usage_contract_value(usage: &ModelUsage) -> Json {
    let mut value = JsonObject::new();
    value.insert("v".to_string(), json!(1));
    for (field, count) in usage.reported() {
        value.insert(field.contract_name().to_string(), json!(count));
    }
    Json::Object(value)
}

pub fn parse_time(value: &Json, path: &str) -> Result<Timestamp, AgentEvidenceError> {
    let (headline, detail) = match value.as_str().map(Timestamp::parse) {
        Some(Ok(timestamp)) => return Ok(timestamp),
        None => ("is absent", "Timestamp is absent."),
        Some(Err(TimestampError::Invalid)) => ("is invalid", "Timestamp is invalid."),
        Some(Err(TimestampError::MissingOffset)) => {
            ("lacks an offset", "Timestamp lacks an offset.")
        }
    };
    Err(AgentEvidenceError::unidentifiable(
        format!("Agent timestamp {path} {headline}."),
        vec![diagnostic("required_identity_missing", path, detail)],
    ))
}

/// The span's duration in nanoseconds: its stored value, or one derived from
/// its interval.
pub fn duration_ns(
    span: &JsonObject,
    start: &Timestamp,
    end: &Timestamp,
) -> Result<i64, AgentEvidenceError> {
    if end < start {
        return Err(AgentEvidenceError::unidentifiable(
            "Span interval ends before it starts.",
            vec![diagnostic(
                "invalid_span_interval",
                "span.interval",
                "Span end time cannot precede start time.",
            )],
        ));
    }
    if let Some(stored) = contract_int(get(span, "duration_ns"), 0) {
        return Ok(stored);
    }
    // The interval has microsecond resolution. It is scaled through floating
    // point seconds, and the result truncated, so every consumer of the same
    // interval derives the same integer.
    let seconds = end.microseconds_since(start) as f64 / 1_000_000.0;
    let derived = (seconds * 1_000_000_000.0) as i64;
    contract_int(&Json::from(derived), 0).ok_or_else(|| {
        AgentEvidenceError::unidentifiable(
            "Agent duration is outside the portable integer domain.",
            vec![diagnostic(
                "invalid_contract_integer",
                "duration_ns",
                "Duration cannot be represented safely in the semantic API.",
            )],
        )
    })
}

pub fn operation_outcome(span: &JsonObject, attributes: &JsonObject) -> Outcome {
    if get(attributes, "junjo.cancelled") == &Json::Bool(true) {
        Outcome::Cancelled
    } else if status_is_error(span) || attributes.contains_key("error.type") {
        Outcome::Failed
    } else {
        Outcome::Completed
    }
}

pub fn status_is_error(span: &JsonObject) -> bool {
    get(span, "status_code").as_str() == Some("2")
}

/// Optional text: null is absent, text is kept, anything else is diagnosed.
fn optional_text(
    value: &Json,
    path: &str,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<String> {
    match value {
        Json::Null => None,
        Json::String(text) => Some(text.clone()),
        _ => {
            diagnostics.push(diagnostic(
                "nonportable_scalar_text",
                path,
                format!("{path} is not interoperable Unicode text."),
            ));
            None
        }
    }
}

/// Whether a value counts as "nothing" where a status message is optional.
fn is_empty_value(value: &Json) -> bool {
    match value {
        Json::Null => true,
        Json::Bool(value) => !value,
        Json::Number(number) => number.as_f64() == Some(0.0),
        Json::String(text) => text.is_empty(),
        Json::Array(items) => items.is_empty(),
        Json::Object(members) => members.is_empty(),
    }
}

/// The attributes of each `exception` event on a span.
fn exception_event_attributes(span: &JsonObject) -> impl Iterator<Item = &JsonObject> {
    get(span, "events_json")
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Json::as_object)
        .filter(|event| get(event, "name").as_str() == Some("exception"))
        .filter_map(|event| get(event, "attributes").as_object())
}

/// The exception types recorded on a span's `exception` events.
pub fn exception_types(span: &JsonObject) -> HashSet<&str> {
    exception_event_attributes(span)
        .filter_map(|attributes| nonempty_text(get(attributes, "exception.type")))
        .collect()
}

pub fn execution_error(
    span: &JsonObject,
    attributes: &JsonObject,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<ExecutionError> {
    let error_type = nonempty_text(get(attributes, "error.type"))?;
    let status_message = get(span, "status_message");
    let mut message = if is_empty_value(status_message) {
        None
    } else {
        optional_text(status_message, "status_message", diagnostics)
    };
    let mut stacktrace = None;
    // The first exception event is the one that describes the failure.
    if let Some(event_attributes) = exception_event_attributes(span).next() {
        let raw_message = get(event_attributes, "exception.message");
        if !raw_message.is_null() {
            message = optional_text(raw_message, "exception.message", diagnostics);
        }
        let raw_stack = get(event_attributes, "exception.stacktrace");
        if !raw_stack.is_null() {
            stacktrace = optional_text(raw_stack, "exception.stacktrace", diagnostics);
        }
    }
    Some(ExecutionError {
        error_type: error_type.to_string(),
        message,
        stacktrace,
    })
}

/// Match OTel's qualified exception type to the semantic error
/// classification. `error.type` is the bare class name; the event may carry
/// the module-qualified one.
pub fn exception_type_matches(error_type: &Json, exception_types: &HashSet<&str>) -> bool {
    let Some(error_type) = nonempty_text(error_type) else {
        return false;
    };
    exception_types.iter().any(|exception_type| {
        *exception_type == error_type || exception_type.rsplit('.').next() == Some(error_type)
    })
}

/// Cancellation evidence for a cancelled execution.
///
/// `Err` means the execution is marked cancelled without a usable reason, so
/// it cannot be represented.
pub fn cancellation_evidence(
    attributes: &JsonObject,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Result<Option<CancellationEvidence>, &'static str> {
    if get(attributes, "junjo.cancelled") != &Json::Bool(true) {
        return Ok(None);
    }
    let reason = optional_text(
        get(attributes, "junjo.cancelled_reason"),
        "junjo.cancelled_reason",
        diagnostics,
    );
    match reason.filter(|reason| !reason.is_empty()) {
        Some(reason) => Ok(Some(CancellationEvidence { reason })),
        None => Err("cancellation evidence requires a reason"),
    }
}

/// Check that an operation's status, error type, exception events, and
/// cancellation flag tell one consistent story.
pub fn validate_operation_transport(
    span: &JsonObject,
    attributes: &JsonObject,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) {
    let outcome = operation_outcome(span, attributes);
    let status_is_error = status_is_error(span);
    let has_error_type = attributes.contains_key("error.type");
    let cancelled = get(attributes, "junjo.cancelled") == &Json::Bool(true);
    let span_path = span_evidence_path(span, "", None);
    let event_path = span_evidence_path(span, "events_json", None);
    match get(span, "events_json") {
        Json::Null => diagnostics.push(diagnostic(
            "missing_operation_event_evidence",
            event_path,
            "Operation event evidence is absent.",
        )),
        Json::Array(events) => {
            for (index, event) in events.iter().enumerate() {
                if !event.is_object() {
                    diagnostics.push(diagnostic(
                        "invalid_operation_event_evidence",
                        format!("{event_path}[{index}]"),
                        "Operation event evidence must contain objects.",
                    ));
                }
            }
        }
        _ => diagnostics.push(diagnostic(
            "invalid_operation_event_evidence",
            event_path,
            "Operation event evidence must be a list.",
        )),
    }
    match outcome {
        Outcome::Failed => {
            let matches =
                exception_type_matches(get(attributes, "error.type"), &exception_types(span));
            if !status_is_error || !matches || cancelled {
                diagnostics.push(diagnostic(
                    "invalid_operation_failure_evidence",
                    span_path,
                    "Failed operation requires matching error status, type, and exception evidence.",
                ));
            }
        }
        Outcome::Cancelled => {
            let has_reason = nonempty_text(get(attributes, "junjo.cancelled_reason")).is_some();
            if !has_reason || status_is_error || has_error_type {
                diagnostics.push(diagnostic(
                    "invalid_operation_cancellation_evidence",
                    span_path,
                    "Cancelled operation requires a reason and non-error transport evidence.",
                ));
            }
        }
        Outcome::Completed => {
            if status_is_error || has_error_type || cancelled {
                diagnostics.push(diagnostic(
                    "invalid_operation_completion_evidence",
                    span_path,
                    "Completed operation cannot carry failure or cancellation evidence.",
                ));
            }
        }
    }
}

/// An object whose member names include every required name and nothing
/// outside the required and optional names.
fn exact_keys<'a>(value: &'a Json, required: &[&str], optional: &[&str]) -> Option<&'a JsonObject> {
    let object = value.as_object()?;
    let complete = required.iter().all(|name| object.contains_key(*name));
    let closed = object
        .keys()
        .all(|name| required.contains(&name.as_str()) || optional.contains(&name.as_str()));
    (complete && closed).then_some(object)
}

fn is_nonempty_string(value: &Json) -> bool {
    nonempty_text(value).is_some()
}

fn valid_tool_descriptor(value: &Json, structural: bool) -> bool {
    let mut required = vec!["name", "description", "inputSchema", "outputSchema"];
    if structural {
        required.push("structuralId");
    }
    let Some(tool) = exact_keys(value, &required, &[]) else {
        return false;
    };
    let fingerprint_shaped = || {
        get(tool, "structuralId")
            .as_str()
            .is_some_and(|id| id.starts_with("tool_sha256:") && id.chars().count() == 76)
    };
    is_nonempty_string(get(tool, "name"))
        && get(tool, "description").is_string()
        && get(tool, "inputSchema").is_object()
        && get(tool, "outputSchema").is_object()
        && (!structural || fingerprint_shaped())
}

/// The RFC 8785 canonical form of structural material.
pub fn canonical_json(material: &Json) -> Result<Vec<u8>, String> {
    serde_jcs::to_vec(material).map_err(|error| error.to_string())
}

/// The structural fingerprint of material: the SHA-256 of its canonical form
/// behind a `<prefix>_sha256:` label.
pub fn structural_fingerprint(prefix: &str, material: &Json) -> Result<String, String> {
    let digest = Sha256::digest(canonical_json(material)?);
    let hex: String = digest.iter().map(|byte| format!("{byte:02x}")).collect();
    Ok(format!("{prefix}_sha256:{hex}"))
}

fn structural_digest(
    prefix: &str,
    material: &Json,
    path: &str,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<String> {
    match structural_fingerprint(prefix, material) {
        Ok(fingerprint) => Some(fingerprint),
        Err(error) => {
            diagnostics.push(diagnostic(
                "invalid_structural_material",
                path,
                format!("Structural material is outside the RFC 8785 I-JSON domain: {error}"),
            ));
            None
        }
    }
}

/// Validate full definition shape, fingerprints, and owner correspondence.
pub fn validate_definition_snapshot(
    payload: &PayloadEvidence,
    owner_attributes: &JsonObject,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<AgentDefinitionContext> {
    const ROOT: &str = "junjo.agent.definition_snapshot";
    if payload.mode != PayloadMode::Full {
        return None;
    }
    let required = [
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
    ];
    let Some(value) = exact_keys(&payload.value, &required, &[]) else {
        diagnostics.push(diagnostic(
            "invalid_definition_snapshot",
            ROOT,
            "Definition shape is invalid.",
        ));
        return None;
    };
    let model = get(value, "model");
    let limits = get(value, "limits");
    let model_is_valid = exact_keys(
        model,
        &["driverKey", "provider", "model", "settings"],
        &["fixture"],
    )
    .is_some_and(|model| {
        is_nonempty_string(get(model, "driverKey"))
            && is_nonempty_string(get(model, "provider"))
            && is_nonempty_string(get(model, "model"))
            && (!model.contains_key("fixture") || get(model, "fixture") == &Json::Bool(true))
            && get(model, "settings").is_object()
    });
    let tools = get(value, "tools")
        .as_array()
        .filter(|tools| tools.iter().all(|tool| valid_tool_descriptor(tool, true)));
    let limits_are_valid =
        exact_keys(limits, &["modelRequests", "toolCalls"], &[]).is_some_and(|limits| {
            contract_int(get(limits, "modelRequests"), 1).is_some()
                && contract_int(get(limits, "toolCalls"), 1).is_some()
        });
    let facts = (
        nonempty_text(get(value, "agentKey")),
        get(value, "instructions").as_str(),
        get(value, "structuralId").as_str(),
        tools,
    );
    let (Some(agent_key), Some(instructions), Some(structural_id), Some(tools)) = facts else {
        diagnostics.push(diagnostic(
            "invalid_definition_snapshot",
            ROOT,
            "Definition values are invalid.",
        ));
        return None;
    };
    if !is_version_one(value)
        || !is_nonempty_string(get(value, "name"))
        || !get(value, "inputSchema").is_object()
        || !get(value, "outputSchema").is_object()
        || !model_is_valid
        || !limits_are_valid
    {
        diagnostics.push(diagnostic(
            "invalid_definition_snapshot",
            ROOT,
            "Definition values are invalid.",
        ));
        return None;
    }

    let mut tool_names = HashSet::new();
    if !tools
        .iter()
        .all(|tool| tool_names.insert(tool["name"].as_str()))
    {
        diagnostics.push(diagnostic(
            "duplicate_tool_definition",
            format!("{ROOT}.tools"),
            "Tool definition names must be unique.",
        ));
    }

    for (index, tool) in tools.iter().enumerate() {
        let material = json!({
            "v": 1,
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["inputSchema"],
            "outputSchema": tool["outputSchema"],
        });
        let expected = structural_digest(
            "tool",
            &material,
            &format!("{ROOT}.tools[{index}]"),
            diagnostics,
        );
        if expected.is_some_and(|expected| tool["structuralId"].as_str() != Some(expected.as_str()))
        {
            diagnostics.push(diagnostic(
                "structural_identity_mismatch",
                format!("{ROOT}.tools[{index}].structuralId"),
                "Tool structural fingerprint does not match its material.",
            ));
        }
    }

    let structural_tools: Vec<Json> = tools
        .iter()
        .map(|tool| {
            json!({
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["inputSchema"],
                "outputSchema": tool["outputSchema"],
            })
        })
        .collect();
    let material = json!({
        "v": 1,
        "agentKey": agent_key,
        "instructions": instructions,
        "inputSchema": value["inputSchema"],
        "model": model,
        "tools": structural_tools,
        "outputSchema": value["outputSchema"],
        "limits": limits,
    });
    let expected_structural_id = structural_digest("agent", &material, ROOT, diagnostics);
    for (key, owner_key) in [
        ("agentKey", "junjo.agent.key"),
        ("name", "junjo.agent.name"),
        ("structuralId", "junjo.executable_structural_id"),
    ] {
        if !values_equal(get(value, key), get(owner_attributes, owner_key)) {
            diagnostics.push(diagnostic(
                "definition_owner_mismatch",
                format!("{ROOT}.{key}"),
                "Definition fact does not match its owner.",
            ));
        }
    }
    if expected_structural_id.is_some_and(|expected| structural_id != expected) {
        diagnostics.push(diagnostic(
            "structural_identity_mismatch",
            format!("{ROOT}.structuralId"),
            "Agent structural fingerprint does not match its material.",
        ));
    }
    let limit_matches = |limit: &str, owner_key: &str| {
        values_equal(member(limits, limit), get(owner_attributes, owner_key))
    };
    if !limit_matches("modelRequests", "junjo.agent.limit.model_requests")
        || !limit_matches("toolCalls", "junjo.agent.limit.tool_calls")
    {
        diagnostics.push(diagnostic(
            "definition_owner_mismatch",
            format!("{ROOT}.limits"),
            "Definition limits do not match owner limits.",
        ));
    }
    Some(AgentDefinitionContext {
        agent_key: agent_key.to_string(),
        instructions: instructions.to_string(),
        tools: structural_tools,
        tool_structural_ids: tools
            .iter()
            .filter_map(|tool| {
                Some((
                    tool["name"].as_str()?.to_string(),
                    tool["structuralId"].as_str()?.to_string(),
                ))
            })
            .collect(),
        output_schema: value["outputSchema"].clone(),
    })
}

fn valid_tool_call(value: &Json) -> bool {
    exact_keys(value, &["id", "name", "arguments"], &[]).is_some_and(|call| {
        is_nonempty_string(get(call, "id"))
            && is_nonempty_string(get(call, "name"))
            && get(call, "arguments").is_object()
    })
}

/// Optional assistant text is absent, null, or text.
fn valid_assistant_text(value: &JsonObject) -> bool {
    matches!(
        value.get("assistantText"),
        None | Some(Json::Null | Json::String(_))
    )
}

fn valid_tool_calls(value: &JsonObject) -> bool {
    get(value, "calls")
        .as_array()
        .is_some_and(|calls| !calls.is_empty() && calls.iter().all(valid_tool_call))
}

fn valid_message(value: &Json) -> bool {
    match member(value, "type").as_str() {
        Some("agent_input") => exact_keys(value, &["type", "input"], &[]).is_some(),
        Some("assistant_output") => exact_keys(value, &["type", "output"], &[]).is_some(),
        Some("assistant_tool_calls") => exact_keys(value, &["type", "calls"], &["assistantText"])
            .is_some_and(|message| valid_tool_calls(message) && valid_assistant_text(message)),
        Some("tool_result") => exact_keys(value, &["type", "callId", "toolName", "result"], &[])
            .is_some_and(|message| {
                is_nonempty_string(get(message, "callId"))
                    && is_nonempty_string(get(message, "toolName"))
            }),
        _ => false,
    }
}

/// Validate a normalized model request and its operation identities.
pub fn validate_model_request(
    payload: &PayloadEvidence,
    operation_attributes: &JsonObject,
    definition: Option<&AgentDefinitionContext>,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) {
    const ROOT: &str = "junjo.agent.model.request";
    if payload.mode != PayloadMode::Full {
        return;
    }
    let required = [
        "v",
        "agentKey",
        "runId",
        "ordinal",
        "instructions",
        "messages",
        "tools",
        "outputSchema",
    ];
    let valid = exact_keys(&payload.value, &required, &[]).filter(|value| {
        is_version_one(value)
            && is_nonempty_string(get(value, "agentKey"))
            && is_nonempty_string(get(value, "runId"))
            && contract_int(get(value, "ordinal"), 1).is_some()
            && get(value, "instructions").is_string()
            && get(value, "messages")
                .as_array()
                .is_some_and(|messages| messages.iter().all(valid_message))
            && get(value, "tools")
                .as_array()
                .is_some_and(|tools| tools.iter().all(|tool| valid_tool_descriptor(tool, false)))
            && get(value, "outputSchema").is_object()
    });
    let Some(value) = valid else {
        diagnostics.push(diagnostic(
            "invalid_model_request",
            ROOT,
            "Normalized request shape is invalid.",
        ));
        return;
    };
    let matches_operation = |member: &str, attribute: &str| {
        values_equal(get(value, member), get(operation_attributes, attribute))
    };
    if !matches_operation("agentKey", "junjo.agent.key")
        || !matches_operation("runId", "junjo.agent.runtime_id")
        || !matches_operation("ordinal", "junjo.agent.model_request.ordinal")
    {
        diagnostics.push(diagnostic(
            "model_request_identity_mismatch",
            ROOT,
            "Request identity does not match operation identity.",
        ));
    }
    let matches_definition = definition.is_none_or(|definition| {
        get(value, "agentKey").as_str() == Some(definition.agent_key.as_str())
            && get(value, "instructions").as_str() == Some(definition.instructions.as_str())
            && values_equal(get(value, "tools"), &Json::Array(definition.tools.clone()))
            && values_equal(get(value, "outputSchema"), &definition.output_schema)
    });
    if !matches_definition {
        diagnostics.push(diagnostic(
            "model_request_definition_mismatch",
            ROOT,
            "Request does not match the Agent definition.",
        ));
    }
}

/// Validate inspectable normalized response content.
///
/// A non-full payload still proves that a normalized response occurred when
/// its scalar response type and payload slot are present. Its transformed
/// content is intentionally outside the original response schema, so it is
/// not checked and this returns `false`.
pub fn validate_model_response(
    payload: &PayloadEvidence,
    response_type: ResponseType,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> bool {
    if payload.mode != PayloadMode::Full {
        return false;
    }
    let shape = match response_type {
        ResponseType::FinalOutput => {
            exact_keys(&payload.value, &["v", "type", "output"], &["usage"])
                .filter(|value| get(value, "type").as_str() == Some("final_output"))
        }
        ResponseType::ToolCalls => exact_keys(
            &payload.value,
            &["v", "type", "calls"],
            &["assistantText", "usage"],
        )
        .filter(|value| {
            get(value, "type").as_str() == Some("tool_calls")
                && valid_tool_calls(value)
                && has_unique_call_ids(value)
                && valid_assistant_text(value)
        }),
    };
    let valid = shape.is_some_and(|value| {
        is_version_one(value) && value.get("usage").is_none_or(valid_response_usage)
    });
    if !valid {
        diagnostics.push(diagnostic(
            "invalid_model_response",
            "junjo.agent.model.response",
            "Normalized response shape is invalid.",
        ));
    }
    valid
}

fn has_unique_call_ids(value: &JsonObject) -> bool {
    let mut seen = HashSet::new();
    get(value, "calls")
        .as_array()
        .is_some_and(|calls| calls.iter().all(|call| seen.insert(call["id"].as_str())))
}

fn valid_response_usage(usage: &Json) -> bool {
    usage.as_object().is_some_and(|usage| {
        is_version_one(usage)
            && usage.iter().all(|(name, item)| {
                name == "v"
                    || (UsageField::from_contract_name(name).is_some()
                        && contract_int(item, 0).is_some())
            })
    })
}
