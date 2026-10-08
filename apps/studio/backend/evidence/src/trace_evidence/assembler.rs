//! Assemble complete normalized spans and verified executable annotations.

use std::collections::{BTreeMap, HashMap, HashSet};

use indexmap::IndexMap;

use crate::agent_diagnostics::assembler::assemble_agent_detail;
use crate::agent_diagnostics::schemas::{AgentOperation, Outcome};
use crate::json::{Json, JsonObject, get};
use crate::store_diagnostics::reconstruction::index_store_spans;
use crate::store_diagnostics::schemas::{
    EvidenceDiagnostic, StoreBoundaryDetail, StoreDetail, StoreTransition,
};
use crate::telemetry_contract::{is_lower_hex, nonempty_text};
use crate::trace_evidence::schemas::{
    AgentExecutableAnnotation, AgentExecutableType, AttemptManifest, DiagnosticScope,
    ExecutableAnnotation, ExecutableManifestEntry, ExecutableRelationships,
    FailureSpanManifestEntry, NormalizedSpanEvidence, OperationManifestEntry, OperationType,
    SelectedSpanEvidence, SelectedSpans, SemanticSpanKind, SpanManifestEntry, StoreAnnotation,
    StoreExecutionDetail, StoreManifestEntry, StoreRole, TraceEvidence, TraceEvidenceDiagnostic,
    TraceManifestSummary, WorkflowExecutableAnnotation,
};
use crate::workflow_diagnostics::assemble_workflow_store_diagnostic;

fn optional_string(value: &Json) -> Option<String> {
    nonempty_text(value).map(str::to_string)
}

fn trace_diagnostic(code: &str, path: String, message: &str) -> TraceEvidenceDiagnostic {
    TraceEvidenceDiagnostic {
        scope: DiagnosticScope::Trace,
        owner_span_id: None,
        issue: EvidenceDiagnostic::new(code, path, message),
    }
}

/// Scope diagnostics to one owner. The owner is named only when its span ID
/// is a valid identity, so the field never carries untrusted text.
fn executable_diagnostics(
    owner_span_id: &str,
    issues: impl IntoIterator<Item = EvidenceDiagnostic>,
) -> impl Iterator<Item = TraceEvidenceDiagnostic> {
    let owner_span_id = is_lower_hex(owner_span_id, 16).then(|| owner_span_id.to_string());
    issues
        .into_iter()
        .map(move |issue| TraceEvidenceDiagnostic {
            scope: DiagnosticScope::Executable,
            owner_span_id: owner_span_id.clone(),
            issue,
        })
}

/// The diagnostics of an owner that could not be annotated. An error that
/// carries none is reported by its own code.
fn semantic_error_diagnostics(
    owner_span_id: &str,
    code: &str,
    message: String,
    diagnostics: Vec<EvidenceDiagnostic>,
) -> impl Iterator<Item = TraceEvidenceDiagnostic> {
    let issues = if diagnostics.is_empty() {
        vec![EvidenceDiagnostic::new(code, "executable", message)]
    } else {
        diagnostics
    };
    executable_diagnostics(owner_span_id, issues)
}

/// Merge one execution's transitions into the shared log of its Store, and
/// return the execution's boundary without them.
///
/// The log holds each physical event once, however many executions observed
/// it. A transition from a verified replay replaces the one already in the
/// log. Any other transition is added only where the log has none.
fn index_store_view(
    stores: &mut IndexMap<String, StoreAnnotation>,
    detail: StoreDetail,
) -> StoreBoundaryDetail {
    let (view, transitions) = detail.into_boundary();
    let Some(store_id) = &view.store_id else {
        return view;
    };
    let store = stores
        .entry(store_id.clone())
        .or_insert_with(|| StoreAnnotation {
            store_id: store_id.clone(),
            transitions: Vec::new(),
        });
    // One event is one sequence on one carrier span with one event ID. The
    // log is kept in that order.
    let event_key =
        |item: &StoreTransition| (item.sequence, item.span_id.clone(), item.event_id.clone());
    let mut by_event: BTreeMap<(i64, String, String), StoreTransition> =
        std::mem::take(&mut store.transitions)
            .into_iter()
            .map(|item| (event_key(&item), item))
            .collect();
    for item in transitions {
        let key = event_key(&item);
        if view.reconstructable || !by_event.contains_key(&key) {
            by_event.insert(key, item);
        }
    }
    store.transitions = by_event.into_values().collect();
    view
}

/// Select the observed interval without treating sibling writers as children.
///
/// A view that is not verified shows no before or after state. The shared
/// log may hold states that another execution's replay produced.
pub fn hydrate_store_view(
    view: &StoreBoundaryDetail,
    stores: &IndexMap<String, StoreAnnotation>,
) -> StoreDetail {
    let store = view
        .store_id
        .as_ref()
        .and_then(|store_id| stores.get(store_id));
    let transitions = match (store, view.sequence_start, view.sequence_end) {
        (Some(store), Some(lower), Some(upper)) => store
            .transitions
            .iter()
            .filter(|item| lower < item.sequence && item.sequence <= upper)
            .map(|item| {
                if view.reconstructable {
                    item.clone()
                } else {
                    StoreTransition {
                        sequence: item.sequence,
                        revision_before: item.revision_before,
                        revision_after: item.revision_after,
                        span_id: item.span_id.clone(),
                        event_id: item.event_id.clone(),
                        action: item.action.clone(),
                        patch: item.patch.clone(),
                        before: Json::Null,
                        after: Json::Null,
                    }
                }
            })
            .collect(),
        _ => Vec::new(),
    };
    view.clone().with_transitions(transitions)
}

/// Keep every raw span while enriching supported executable owners.
pub fn assemble_trace_evidence(
    trace_id: &str,
    spans: Vec<NormalizedSpanEvidence>,
) -> TraceEvidence {
    let objects: Vec<JsonObject> = spans
        .iter()
        .map(NormalizedSpanEvidence::to_object)
        .collect();
    let trace_spans: Vec<&JsonObject> = objects.iter().collect();
    let store_index = index_store_spans(&trace_spans);
    let mut executables = IndexMap::new();
    let mut operations = IndexMap::new();
    let mut stores = IndexMap::new();
    let mut relationships = IndexMap::new();
    let mut diagnostics = Vec::new();

    for (span, object) in spans.iter().zip(&objects) {
        let owner_span_id = span.span_id.as_str();
        if span.trace_id != trace_id {
            diagnostics.push(trace_diagnostic(
                "trace_identity_mismatch",
                format!("span[{owner_span_id}].trace_id"),
                "Span trace identity does not match the requested trace.",
            ));
        }

        match get(&span.attributes_json, "junjo.span_type").as_str() {
            Some("agent") => {
                let detail = match assemble_agent_detail(object, &trace_spans, Some(&store_index)) {
                    Ok(detail) => detail,
                    Err(error) => {
                        diagnostics.extend(semantic_error_diagnostics(
                            owner_span_id,
                            error.code.as_str(),
                            error.message,
                            error.diagnostics,
                        ));
                        continue;
                    }
                };
                let runtime_id = detail.summary.runtime_id.clone();
                diagnostics.extend(executable_diagnostics(
                    owner_span_id,
                    detail.integrity.diagnostics.iter().cloned(),
                ));
                operations.insert(
                    runtime_id.clone(),
                    detail
                        .operations
                        .into_iter()
                        .map(|operation| (operation.span_id().to_string(), operation))
                        .collect::<IndexMap<String, AgentOperation>>(),
                );
                relationships.insert(
                    owner_span_id.to_string(),
                    ExecutableRelationships {
                        parent: detail.parent_executable,
                        nested: detail.nested_executables,
                    },
                );
                let runtime_view = index_store_view(&mut stores, detail.state);
                let application_view = index_store_view(&mut stores, detail.application_state);
                executables.insert(
                    owner_span_id.to_string(),
                    ExecutableAnnotation::Agent(Box::new(AgentExecutableAnnotation {
                        executable_type: AgentExecutableType::Agent,
                        owner_span_id: owner_span_id.to_string(),
                        runtime_id,
                        stores: IndexMap::from([
                            (StoreRole::Runtime, runtime_view),
                            (StoreRole::Application, application_view),
                        ]),
                        summary: detail.summary,
                        definition: detail.definition,
                        input: detail.input,
                        output: detail.output,
                        input_candidate: detail.input_candidate,
                        history_candidate: detail.history_candidate,
                        error: detail.error,
                        cancellation: detail.cancellation,
                        integrity: detail.integrity,
                    })),
                );
            }
            Some("workflow" | "subflow") => {
                let detail = match assemble_workflow_store_diagnostic(
                    object,
                    &trace_spans,
                    Some(&store_index),
                ) {
                    Ok(detail) => detail,
                    Err(error) => {
                        diagnostics.extend(semantic_error_diagnostics(
                            owner_span_id,
                            error.code.as_str(),
                            error.message,
                            error.diagnostics,
                        ));
                        continue;
                    }
                };
                let attributes = &span.attributes_json;
                let runtime_id = optional_string(get(attributes, "junjo.executable_runtime_id"));
                diagnostics.extend(executable_diagnostics(
                    owner_span_id,
                    detail.integrity.diagnostics.iter().cloned(),
                ));
                let application_view = index_store_view(&mut stores, detail.state);
                executables.insert(
                    owner_span_id.to_string(),
                    ExecutableAnnotation::Workflow(Box::new(WorkflowExecutableAnnotation {
                        executable_type: detail.executable_type,
                        owner_span_id: owner_span_id.to_string(),
                        name: detail.name,
                        definition_id: optional_string(get(
                            attributes,
                            "junjo.executable_definition_id",
                        )),
                        runtime_id,
                        structural_id: optional_string(get(
                            attributes,
                            "junjo.executable_structural_id",
                        )),
                        stores: IndexMap::from([(StoreRole::Application, application_view)]),
                        integrity: detail.integrity,
                    })),
                );
            }
            _ => {}
        }
    }

    // The roles each Store ID is used under, across every execution. An
    // Agent's private runtime Store has exactly one user.
    let mut store_users: IndexMap<&str, Vec<StoreRole>> = IndexMap::new();
    for executable in executables.values() {
        for (role, view) in executable.stores() {
            if let Some(store_id) = &view.store_id {
                store_users.entry(store_id).or_default().push(*role);
            }
        }
    }
    for (store_id, roles) in store_users {
        if roles.len() > 1 && roles.contains(&StoreRole::Runtime) {
            diagnostics.push(trace_diagnostic(
                "runtime_store_identity_conflict",
                format!("stores.{store_id}"),
                "Private Agent runtime Stores cannot be borrowed by other executions.",
            ));
        }
    }

    TraceEvidence {
        trace_id: trace_id.to_string(),
        spans,
        executables_by_span_id: executables,
        operations_by_owner_runtime_id: operations,
        stores_by_id: stores,
        relationships_by_owner_span_id: relationships,
        diagnostics,
    }
}

/// Classify a span by Junjo semantics first, then by the GenAI and
/// OpenInference conventions other instrumentation emits.
fn semantic_kind(span: &NormalizedSpanEvidence) -> SemanticSpanKind {
    let attribute = |key: &str| get(&span.attributes_json, key).as_str();
    match attribute("junjo.agent.operation_type") {
        Some("model_request") => return SemanticSpanKind::Model,
        Some("tool") => return SemanticSpanKind::Tool,
        _ => {}
    }
    match attribute("junjo.span_type") {
        Some("agent") => return SemanticSpanKind::Agent,
        Some("workflow") => return SemanticSpanKind::Workflow,
        Some("subflow") => return SemanticSpanKind::Subflow,
        Some("node") => return SemanticSpanKind::Node,
        Some("run_concurrent") => return SemanticSpanKind::RunConcurrent,
        _ => {}
    }
    match attribute("gen_ai.operation.name") {
        Some("chat" | "text_completion" | "generate_content" | "responses") => {
            return SemanticSpanKind::Model;
        }
        Some("execute_tool") => return SemanticSpanKind::Tool,
        Some("invoke_agent") => return SemanticSpanKind::Agent,
        Some("invoke_workflow") => return SemanticSpanKind::Workflow,
        _ => {}
    }
    match attribute("openinference.span.kind")
        .map(str::to_uppercase)
        .as_deref()
    {
        Some("LLM") => SemanticSpanKind::Model,
        Some("TOOL") => SemanticSpanKind::Tool,
        _ => SemanticSpanKind::Span,
    }
}

/// The model or Tool name a span declares, or the span's own name.
fn operation_name(span: &NormalizedSpanEvidence, kind: SemanticSpanKind) -> String {
    let candidates: &[&str] = if kind == SemanticSpanKind::Model {
        &[
            "junjo.agent.model.name",
            "gen_ai.response.model",
            "gen_ai.request.model",
            "llm.model_name",
        ]
    } else {
        &["junjo.agent.tool.name", "gen_ai.tool.name", "tool.name"]
    };
    candidates
        .iter()
        .find_map(|key| optional_string(get(&span.attributes_json, key)))
        .unwrap_or_else(|| span.name.clone())
}

/// Whether a value is present and not an empty or zero value.
fn is_set(value: &Json) -> bool {
    match value {
        Json::Null => false,
        Json::Bool(value) => *value,
        Json::Number(number) => number.as_f64() != Some(0.0),
        Json::String(text) => !text.is_empty(),
        Json::Array(items) => !items.is_empty(),
        Json::Object(members) => !members.is_empty(),
    }
}

/// The attributes of each event that reports a failure.
fn failure_events(span: &NormalizedSpanEvidence) -> impl Iterator<Item = &JsonObject> {
    span.events_json
        .iter()
        .filter_map(Json::as_object)
        .filter(|event| {
            matches!(
                get(event, "name").as_str(),
                Some("exception" | "junjo.hook_error")
            )
        })
}

fn is_failed(span: &NormalizedSpanEvidence) -> bool {
    matches!(
        span.status_code.to_uppercase().as_str(),
        "2" | "ERROR" | "STATUS_CODE_ERROR"
    ) || is_set(get(&span.attributes_json, "error.type"))
        || failure_events(span).next().is_some()
}

/// The exception type, the message, and whether a stack trace exists. Later
/// events override earlier ones, and events override span attributes.
fn failure_fields(span: &NormalizedSpanEvidence) -> (Option<String>, Option<String>, bool) {
    let mut exception_type = optional_string(get(&span.attributes_json, "error.type"));
    let mut exception_message = optional_string(get(&span.attributes_json, "error.message"));
    let mut has_stacktrace = false;
    for event in failure_events(span) {
        let Some(attributes) = get(event, "attributes").as_object() else {
            continue;
        };
        let first = |keys: [&str; 2]| {
            keys.iter()
                .find_map(|key| optional_string(get(attributes, key)))
        };
        exception_type = first(["exception.type", "junjo.hook.error.type"]).or(exception_type);
        exception_message =
            first(["exception.message", "junjo.hook.error.message"]).or(exception_message);
        if nonempty_text(get(attributes, "exception.stacktrace")).is_some() {
            has_stacktrace = true;
        }
    }
    let status_message = || (!span.status_message.is_empty()).then(|| span.status_message.clone());
    (
        exception_type,
        exception_message.or_else(status_message),
        has_stacktrace,
    )
}

/// Lookups shared by the manifest and the span selection.
struct EvidenceIndex<'a> {
    spans_by_id: HashMap<&'a str, &'a NormalizedSpanEvidence>,
    /// Each verified operation with the runtime ID of the Agent that owns it.
    operations_by_span_id: HashMap<&'a str, (&'a str, &'a AgentOperation)>,
    owner_span_id_by_runtime_id: HashMap<&'a str, &'a str>,
    executable_span_ids: HashSet<&'a str>,
}

impl<'a> EvidenceIndex<'a> {
    fn new(evidence: &'a TraceEvidence) -> Self {
        Self {
            spans_by_id: evidence
                .spans
                .iter()
                .map(|span| (span.span_id.as_str(), span))
                .collect(),
            operations_by_span_id: evidence
                .operations_by_owner_runtime_id
                .iter()
                .flat_map(|(runtime_id, operations)| {
                    operations.iter().map(move |(span_id, operation)| {
                        (span_id.as_str(), (runtime_id.as_str(), operation))
                    })
                })
                .collect(),
            owner_span_id_by_runtime_id: evidence
                .executables_by_span_id
                .iter()
                .filter_map(|(owner_span_id, executable)| {
                    Some((executable.runtime_id()?, owner_span_id.as_str()))
                })
                .collect(),
            executable_span_ids: evidence
                .executables_by_span_id
                .keys()
                .map(String::as_str)
                .collect(),
        }
    }

    /// The span itself when it is an executable owner, or its nearest
    /// ancestor that is one.
    fn nearest_executable_owner(&self, span: &NormalizedSpanEvidence) -> Option<&'a str> {
        if let Some(owner) = self.executable_span_ids.get(span.span_id.as_str()) {
            return Some(owner);
        }
        let mut parent_span_id = span.parent_span_id.as_deref();
        let mut visited = HashSet::new();
        while let Some(current) = parent_span_id {
            if !visited.insert(current) {
                return None;
            }
            if let Some(owner) = self.executable_span_ids.get(current) {
                return Some(owner);
            }
            parent_span_id = self.spans_by_id.get(current)?.parent_span_id.as_deref();
        }
        None
    }

    /// The owner of one span as `(owner span ID, owner runtime ID)`.
    ///
    /// A verified operation belongs to the Agent whose runtime ID it carries.
    /// Any other span belongs to its nearest executable ancestor.
    fn span_owner(
        &self,
        evidence: &TraceEvidence,
        span: &NormalizedSpanEvidence,
    ) -> (Option<String>, Option<String>) {
        if let Some((owner_runtime_id, _)) = self.operations_by_span_id.get(span.span_id.as_str()) {
            let owner_span_id = self.owner_span_id_by_runtime_id.get(owner_runtime_id);
            return (
                owner_span_id.map(|id| (*id).to_string()),
                Some((*owner_runtime_id).to_string()),
            );
        }
        let owner_span_id = self.nearest_executable_owner(span);
        let owner_runtime_id = owner_span_id
            .and_then(|owner_span_id| evidence.executables_by_span_id.get(owner_span_id))
            .and_then(ExecutableAnnotation::runtime_id);
        (
            owner_span_id.map(str::to_string),
            owner_runtime_id.map(str::to_string),
        )
    }
}

/// The Studio path of one span.
pub fn span_path(service_name: &str, trace_id: &str, span_id: &str) -> String {
    format!(
        "/traces/{}/{trace_id}/{span_id}",
        percent_encode(service_name)
    )
}

/// Percent-encode one path segment, leaving only unreserved characters.
pub fn percent_encode(segment: &str) -> String {
    let mut encoded = String::with_capacity(segment.len());
    for byte in segment.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b'-' | b'~') {
            encoded.push(char::from(byte));
        } else {
            encoded.push_str(&format!("%{byte:02X}"));
        }
    }
    encoded
}

/// Project one complete trace into a selectable, payload-light manifest.
///
/// `service_name` is the Attempt subject's service, used for span paths.
pub fn assemble_attempt_evidence_manifest(
    service_name: &str,
    evidence: &TraceEvidence,
) -> AttemptManifest {
    let index = EvidenceIndex::new(evidence);

    let mut span_entries = Vec::with_capacity(evidence.spans.len());
    let mut failures = Vec::new();
    for span in &evidence.spans {
        let failed = is_failed(span);
        let span_path = span_path(service_name, &evidence.trace_id, &span.span_id);
        let kind = semantic_kind(span);
        span_entries.push(SpanManifestEntry {
            span_id: span.span_id.clone(),
            parent_span_id: span.parent_span_id.clone(),
            name: span.name.clone(),
            semantic_kind: kind,
            status_code: span.status_code.clone(),
            start_time: span.start_time.clone(),
            end_time: span.end_time.clone(),
            failed,
            span_path: span_path.clone(),
        });
        if !failed {
            continue;
        }
        let (owner_span_id, owner_runtime_id) = index.span_owner(evidence, span);
        let (exception_type, exception_message, stacktrace_available) = failure_fields(span);
        failures.push(FailureSpanManifestEntry {
            span_id: span.span_id.clone(),
            parent_span_id: span.parent_span_id.clone(),
            name: span.name.clone(),
            semantic_kind: kind,
            status_code: span.status_code.clone(),
            start_time: span.start_time.clone(),
            end_time: span.end_time.clone(),
            exception_type,
            exception_message,
            stacktrace_available,
            owner_span_id,
            owner_runtime_id,
            span_path,
        });
    }

    let mut executables = Vec::with_capacity(evidence.executables_by_span_id.len());
    let mut stores = Vec::new();
    for (owner_span_id, executable) in &evidence.executables_by_span_id {
        let Some(owner_span) = index.spans_by_id.get(owner_span_id.as_str()) else {
            continue;
        };
        let failed = is_failed(owner_span);
        let (name, outcome) = match executable {
            ExecutableAnnotation::Agent(annotation) => (
                annotation.summary.agent_name.clone(),
                Some(annotation.summary.outcome),
            ),
            ExecutableAnnotation::Workflow(annotation) => {
                (annotation.name.clone(), failed.then_some(Outcome::Failed))
            }
        };
        executables.push(ExecutableManifestEntry {
            owner_span_id: owner_span_id.clone(),
            executable_type: executable.executable_type(),
            name,
            runtime_id: executable.runtime_id().map(str::to_string),
            store_ids: executable
                .stores()
                .iter()
                .map(|(role, view)| (*role, view.store_id.clone()))
                .collect(),
            outcome,
            status_code: owner_span.status_code.clone(),
            failed,
            integrity: executable.integrity().clone(),
        });

        // One entry for each role a Store plays for this executable.
        for (role, detail) in executable.stores() {
            stores.push(StoreManifestEntry {
                store_id: detail.store_id.clone(),
                owner_span_id: owner_span_id.clone(),
                owner_runtime_id: executable.runtime_id().map(str::to_string),
                owner_executable_type: executable.executable_type(),
                role: *role,
                sequence_start: detail.sequence_start,
                sequence_end: detail.sequence_end,
                available: detail.available,
                transition_count: detail.transition_count,
                reconstructable: detail.reconstructable,
                reconstruction_status: detail.reconstruction_status,
                integrity: executable.integrity().clone(),
            });
        }
    }

    let mut operations = Vec::new();
    let mut operation_span_ids = HashSet::new();
    for span in &evidence.spans {
        let kind = semantic_kind(span);
        let is_operation = matches!(kind, SemanticSpanKind::Model | SemanticSpanKind::Tool);
        if !is_operation || !operation_span_ids.insert(span.span_id.as_str()) {
            continue;
        }
        let (owner_span_id, owner_runtime_id) = index.span_owner(evidence, span);
        let verified = index.operations_by_span_id.get(span.span_id.as_str());
        let (name, outcome, duration_ns, error_type, error_message) = match verified {
            Some((_, AgentOperation::Model(operation))) => (
                operation.model_name.clone(),
                operation.outcome,
                Some(operation.duration_ns),
                operation
                    .error
                    .as_ref()
                    .map(|error| error.error_type.clone()),
                operation
                    .error
                    .as_ref()
                    .and_then(|error| error.message.clone()),
            ),
            Some((_, AgentOperation::Tool(operation))) => (
                operation.tool_name.clone(),
                operation.outcome,
                Some(operation.duration_ns),
                operation
                    .error
                    .as_ref()
                    .map(|error| error.error_type.clone()),
                operation
                    .error
                    .as_ref()
                    .and_then(|error| error.message.clone()),
            ),
            None => {
                let (error_type, error_message, _) = failure_fields(span);
                let outcome = if is_failed(span) {
                    Outcome::Failed
                } else {
                    Outcome::Completed
                };
                (
                    operation_name(span, kind),
                    outcome,
                    None,
                    error_type,
                    error_message,
                )
            }
        };
        operations.push(OperationManifestEntry {
            owner_span_id,
            owner_runtime_id,
            span_id: span.span_id.clone(),
            operation_type: if kind == SemanticSpanKind::Model {
                OperationType::ModelRequest
            } else {
                OperationType::Tool
            },
            name,
            outcome,
            duration_ns,
            error_type,
            error_message,
        });
    }

    AttemptManifest {
        trace: TraceManifestSummary {
            trace_id: evidence.trace_id.clone(),
            span_count: evidence.spans.len(),
            root_span_ids: evidence
                .spans
                .iter()
                .filter(|span| span.parent_span_id.is_none())
                .map(|span| span.span_id.clone())
                .collect(),
        },
        spans: span_entries,
        failures,
        executables,
        operations,
        stores,
        relationships_by_owner_span_id: evidence.relationships_by_owner_span_id.clone(),
        diagnostics: evidence.diagnostics.clone(),
    }
}

/// Return complete evidence for explicit span identities in caller order.
pub fn select_attempt_span_evidence(
    evidence: &TraceEvidence,
    span_ids: &[String],
) -> SelectedSpans {
    let index = EvidenceIndex::new(evidence);
    let mut items = Vec::new();
    let mut missing_span_ids = Vec::new();
    for span_id in span_ids {
        let Some(span) = index.spans_by_id.get(span_id.as_str()) else {
            missing_span_ids.push(span_id.clone());
            continue;
        };
        items.push(SelectedSpanEvidence {
            span: (*span).clone(),
            executable: evidence.executables_by_span_id.get(span_id).cloned(),
            operation: index
                .operations_by_span_id
                .get(span_id.as_str())
                .map(|(_, operation)| (*operation).clone()),
            stores: evidence
                .executables_by_span_id
                .get(span_id)
                .into_iter()
                .flat_map(ExecutableAnnotation::stores)
                .map(|(role, view)| StoreExecutionDetail {
                    owner_span_id: span_id.clone(),
                    role: *role,
                    detail: hydrate_store_view(view, &evidence.stores_by_id),
                })
                .collect(),
            relationships: evidence
                .relationships_by_owner_span_id
                .get(span_id)
                .cloned(),
            diagnostics: evidence
                .diagnostics
                .iter()
                .filter(|diagnostic| diagnostic.owner_span_id.as_ref() == Some(span_id))
                .cloned()
                .collect(),
        });
    }
    SelectedSpans {
        items,
        missing_span_ids,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn path_segments_keep_only_unreserved_characters() {
        assert_eq!(percent_encode("svc-a_b.c~d"), "svc-a_b.c~d");
        assert_eq!(percent_encode("a b/c?d"), "a%20b%2Fc%3Fd");
        assert_eq!(percent_encode("café"), "caf%C3%A9");
        assert_eq!(
            span_path("my service", "t", "s"),
            "/traces/my%20service/t/s"
        );
    }
}
