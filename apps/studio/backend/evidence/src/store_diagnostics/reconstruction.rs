//! Owner-scoped Store reconstruction and evidence integrity verification.

use std::collections::{HashMap, HashSet};

use crate::json::{Json, JsonObject, get, values_equal};
use crate::spans::attributes;
use crate::store_diagnostics::json_patch::apply_patch;
use crate::store_diagnostics::payloads::parse_required_payload_slot;
use crate::store_diagnostics::schemas::{
    EvidenceDiagnostic, PayloadMode, ReconstructionStatus, StoreDetail, StoreTransition,
};
use crate::telemetry_contract::{
    contract_int, is_active_contract_version, is_lower_hex, nonempty_text, span_evidence_path,
};

/// Store projection plus diagnostics owned by the enclosing detail integrity.
#[derive(Debug, Clone, PartialEq)]
pub struct StoreReconstructionResult {
    pub detail: StoreDetail,
    pub diagnostics: Vec<EvidenceDiagnostic>,
    pub replay_verified: bool,
}

/// Executable-specific attribute names for one generic Store contract.
#[derive(Debug)]
pub struct StoreOwnerBoundary {
    pub store_id_attribute: &'static str,
    pub state_start_root: &'static str,
    pub state_end_root: &'static str,
    pub metadata_prefix: &'static str,
    pub availability_attribute: Option<&'static str>,
    pub unavailable_owner_prefixes: &'static [&'static str],
    pub runtime_id_attribute: Option<&'static str>,
}

pub const AGENT_STORE_BOUNDARY: StoreOwnerBoundary = StoreOwnerBoundary {
    store_id_attribute: "junjo.agent.store.id",
    state_start_root: "junjo.agent.state.start",
    state_end_root: "junjo.agent.state.end",
    metadata_prefix: "junjo.store",
    availability_attribute: Some("junjo.agent.state.available"),
    unavailable_owner_prefixes: &[
        "junjo.agent.store",
        "junjo.agent.state.start",
        "junjo.agent.state.end",
        "junjo.store.",
    ],
    runtime_id_attribute: Some("junjo.agent.runtime_id"),
};

pub const AGENT_APPLICATION_STORE_BOUNDARY: StoreOwnerBoundary = StoreOwnerBoundary {
    store_id_attribute: "junjo.agent.application_store.id",
    state_start_root: "junjo.agent.application_state.start",
    state_end_root: "junjo.agent.application_state.end",
    metadata_prefix: "junjo.agent.application_store",
    availability_attribute: Some("junjo.agent.application_state.available"),
    unavailable_owner_prefixes: &[
        "junjo.agent.application_store.",
        "junjo.agent.application_state.start",
        "junjo.agent.application_state.end",
    ],
    runtime_id_attribute: None,
};

pub const WORKFLOW_STORE_BOUNDARY: StoreOwnerBoundary = StoreOwnerBoundary {
    store_id_attribute: "junjo.workflow.store.id",
    state_start_root: "junjo.workflow.state.start",
    state_end_root: "junjo.workflow.state.end",
    metadata_prefix: "junjo.store",
    availability_attribute: None,
    unavailable_owner_prefixes: &[],
    runtime_id_attribute: None,
};

const SEQUENCE: &str = "junjo.store.transition.sequence";

/// The `set_state` events of one span that belong to `store_id`, with their
/// attributes.
pub(crate) fn owned_store_events<'a>(
    span: &'a JsonObject,
    store_id: &'a str,
) -> impl Iterator<Item = &'a JsonObject> {
    get(span, "events_json")
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(move |event| store_event_attributes(event, store_id))
}

/// The attributes of `event` when it is a `set_state` event for `store_id`.
fn store_event_attributes<'a>(event: &'a Json, store_id: &str) -> Option<&'a JsonObject> {
    let event = event.as_object()?;
    let attributes = get(event, "attributes").as_object()?;
    let is_set_state = get(event, "name").as_str() == Some("set_state");
    let is_this_store = get(attributes, "junjo.store.id").as_str() == Some(store_id);
    (is_set_state && is_this_store).then_some(attributes)
}

/// A state-unavailable executable has no Store. Any Store fact on the owner,
/// or Store event on a span that carries its runtime identity, is fabricated.
fn unavailable_store_is_fabricated(
    owner_attributes: &JsonObject,
    spans: &[&JsonObject],
    boundary: &StoreOwnerBoundary,
) -> bool {
    let has_forbidden_fact = owner_attributes.keys().any(|key| {
        boundary
            .unavailable_owner_prefixes
            .iter()
            .any(|prefix| key.starts_with(prefix))
    });
    if has_forbidden_fact {
        return true;
    }
    let Some(runtime_attribute) = boundary.runtime_id_attribute else {
        return false;
    };
    let Some(runtime_id) = nonempty_text(get(owner_attributes, runtime_attribute)) else {
        return false;
    };
    spans.iter().any(|span| {
        let owned = get(span, "attributes_json")
            .as_object()
            .is_some_and(|attributes| {
                get(attributes, runtime_attribute).as_str() == Some(runtime_id)
            });
        owned
            && get(span, "events_json")
                .as_array()
                .into_iter()
                .flatten()
                .any(|event| {
                    let Some(event) = event.as_object() else {
                        return false;
                    };
                    get(event, "name").as_str() == Some("set_state")
                        && get(event, "attributes")
                            .as_object()
                            .is_some_and(|attributes| attributes.contains_key("junjo.store.id"))
                })
    })
}

fn failed(diagnostics: Vec<EvidenceDiagnostic>, detail: StoreDetail) -> StoreReconstructionResult {
    StoreReconstructionResult {
        detail,
        diagnostics,
        replay_verified: false,
    }
}

/// Reconstruct one executable-owned Store from contract v3 evidence.
pub fn reconstruct_store(
    owner_attributes: &JsonObject,
    spans: &[&JsonObject],
    boundary: &StoreOwnerBoundary,
) -> StoreReconstructionResult {
    if let Some(availability_attribute) = boundary.availability_attribute {
        match get(owner_attributes, availability_attribute) {
            Json::Bool(true) => {}
            Json::Bool(false) => {
                let mut diagnostics = Vec::new();
                if unavailable_store_is_fabricated(owner_attributes, spans, boundary) {
                    diagnostics.push(EvidenceDiagnostic::new(
                        "fabricated_boundary_store",
                        availability_attribute,
                        "State-unavailable executable cannot carry Store facts or events.",
                    ));
                }
                return failed(diagnostics, StoreDetail::unavailable("state_unavailable"));
            }
            _ => {
                return failed(
                    vec![EvidenceDiagnostic::new(
                        "invalid_store_owner_fact",
                        availability_attribute,
                        "State availability is absent or invalid.",
                    )],
                    StoreDetail::unavailable("invalid_state_availability"),
                );
            }
        }
    }

    let mut diagnostics = Vec::new();
    let Some(store_id) = nonempty_text(get(owner_attributes, boundary.store_id_attribute)) else {
        diagnostics.push(EvidenceDiagnostic::new(
            "missing_store_id",
            boundary.store_id_attribute,
            "Store ID is absent or invalid.",
        ));
        return failed(
            diagnostics,
            StoreDetail {
                available: true,
                reconstruction_status: ReconstructionStatus::Failed,
                reconstruction_reason: Some("missing_store_id".to_string()),
                ..StoreDetail::unavailable("")
            },
        );
    };

    let start = parse_required_payload_slot(
        owner_attributes,
        boundary.state_start_root,
        &mut diagnostics,
    );
    let end =
        parse_required_payload_slot(owner_attributes, boundary.state_end_root, &mut diagnostics);
    // The owner's Store facts are named under the boundary's metadata prefix.
    let fact_key = |suffix: &str| format!("{}.{suffix}", boundary.metadata_prefix);
    let fact = |suffix: &str| get(owner_attributes, &fact_key(suffix));
    let sequence_start = fact("transition.start");
    let sequence_end = fact("transition.end");
    let revision_start = fact("revision.start");
    let revision_end = fact("revision.end");
    let transition_count = fact("transition.count");
    for (suffix, value) in [
        ("transition.start", sequence_start),
        ("transition.end", sequence_end),
        ("revision.start", revision_start),
        ("revision.end", revision_end),
        ("transition.count", transition_count),
    ] {
        if contract_int(value, 0).is_none() {
            let key = fact_key(suffix);
            diagnostics.push(EvidenceDiagnostic::new(
                "invalid_store_owner_fact",
                key.as_str(),
                format!("{key} is invalid."),
            ));
        }
    }
    let reconstructable_claimed = fact("reconstructable").as_bool();
    if reconstructable_claimed.is_none() {
        diagnostics.push(EvidenceDiagnostic::new(
            "invalid_store_owner_fact",
            fact_key("reconstructable"),
            "Reconstructability claim is invalid.",
        ));
    }

    // This execution observed the transitions after the start sequence, up
    // to and including the end sequence: `(lower, upper]`.
    let interval = contract_int(sequence_start, 0).zip(contract_int(sequence_end, 0));
    if let Some((lower, upper)) = interval
        && (upper < lower || !values_equal(&Json::from(upper - lower), transition_count))
    {
        diagnostics.push(EvidenceDiagnostic::new(
            "invalid_store_interval",
            fact_key("transition"),
            "Transition bounds must be ordered and agree with the transition count.",
        ));
    }

    // Every `set_state` event for this Store that this execution observed,
    // with the span that carried it.
    let mut raw_events: Vec<(&str, &JsonObject)> = Vec::new();
    let mut observed_store_name: Option<&str> = None;
    for (span_index, span) in spans.iter().enumerate() {
        let span_id = get(span, "span_id")
            .as_str()
            .filter(|id| is_lower_hex(id, 16));
        let mut invalid_span_id_diagnosed = false;
        let events = match span.get("events_json") {
            None => &[][..],
            Some(Json::Array(events)) => events.as_slice(),
            Some(_) => {
                diagnostics.push(EvidenceDiagnostic::new(
                    "invalid_store_event",
                    format!("spans[{span_index}].events"),
                    "Events are invalid.",
                ));
                continue;
            }
        };
        for (event_index, event) in events.iter().enumerate() {
            if !event.is_object() {
                diagnostics.push(EvidenceDiagnostic::new(
                    "invalid_store_event",
                    format!("spans[{span_index}].events[{event_index}]"),
                    "Store event is invalid.",
                ));
                continue;
            }
            let Some(attributes) = store_event_attributes(event, store_id) else {
                continue;
            };
            // A transition outside the interval belongs to another
            // execution's view of the same Store.
            if let Some((lower, upper)) = interval
                && let Some(sequence) = contract_int(get(attributes, SEQUENCE), 0)
                && !(lower < sequence && sequence <= upper)
            {
                continue;
            }
            let Some(span_id) = span_id else {
                if !invalid_span_id_diagnosed {
                    diagnostics.push(EvidenceDiagnostic::new(
                        "invalid_span_id",
                        format!("spans[{span_index}].span_id"),
                        "Store transition carrier span ID must be 16 lowercase hexadecimal characters.",
                    ));
                    invalid_span_id_diagnosed = true;
                }
                continue;
            };
            let name_path = format!("spans[{span_index}].events[{event_index}].junjo.store.name");
            match (
                nonempty_text(get(attributes, "junjo.store.name")),
                observed_store_name,
            ) {
                (None, _) => diagnostics.push(EvidenceDiagnostic::new(
                    "invalid_store_name",
                    name_path,
                    "Store transition name is absent or invalid.",
                )),
                (Some(name), None) => observed_store_name = Some(name),
                (Some(name), Some(observed)) if name != observed => {
                    diagnostics.push(EvidenceDiagnostic::new(
                        "invalid_store_name",
                        name_path,
                        "One Store ID must use one consistent Store name.",
                    ));
                }
                (Some(_), Some(_)) => {}
            }
            raw_events.push((span_id, attributes));
        }
    }

    let mut integer_sequences: Vec<i64> = raw_events
        .iter()
        .filter_map(|(_, attributes)| contract_int(get(attributes, SEQUENCE), 0))
        .collect();
    if integer_sequences.len() != raw_events.len() {
        diagnostics.push(EvidenceDiagnostic::new(
            "transition_sequence_out_of_range",
            "events",
            "A transition sequence is invalid.",
        ));
    }
    integer_sequences.sort_unstable();
    if integer_sequences.windows(2).any(|pair| pair[0] == pair[1]) {
        diagnostics.push(EvidenceDiagnostic::new(
            "transition_sequence_duplicate",
            "events",
            "Transition sequences are duplicated.",
        ));
    }
    if let Some((lower, upper)) = interval
        && upper >= lower
    {
        // The expected sequences follow the lower bound, one by one, through
        // the upper bound.
        let contiguous = integer_sequences
            .iter()
            .zip(lower + 1..)
            .all(|(observed, expected)| *observed == expected);
        if !contiguous || integer_sequences.len() as i64 != upper - lower {
            let code = if contiguous {
                "transition_sequence_missing_trailing"
            } else {
                "transition_sequence_gap"
            };
            diagnostics.push(EvidenceDiagnostic::new(
                code,
                "events",
                "Transition sequence is incomplete.",
            ));
        }
    }

    let comparable = end.mode == start.mode && end.policy == start.policy;
    let inline_replay = comparable && start.mode.is_inline();
    let mut policy_unavailable =
        comparable && matches!(start.mode, PayloadMode::Excluded | PayloadMode::Reference);
    if !inline_replay && !policy_unavailable {
        diagnostics.push(EvidenceDiagnostic::new(
            "payload_policy_mismatch",
            format!("{}/{}", boundary.state_start_root, boundary.state_end_root),
            "Store start and end evidence must use one comparable payload mode and policy.",
        ));
    }

    let mut transitions = Vec::new();
    let mut current_state = if inline_replay {
        start.value.clone()
    } else {
        Json::Null
    };
    let mut current_revision = contract_int(revision_start, 0);
    let mut replay_possible = inline_replay && diagnostics.is_empty();

    // Valid sequences first, in order, with the carrier span breaking ties.
    // Events without a usable sequence follow; each only adds a diagnostic.
    raw_events.sort_by_key(|(span_id, attributes)| {
        match contract_int(get(attributes, SEQUENCE), 0) {
            Some(sequence) => (0, sequence, *span_id),
            None => (1, 0, ""),
        }
    });
    for (span_id, attributes) in raw_events {
        let facts = (
            contract_int(get(attributes, SEQUENCE), 1),
            contract_int(get(attributes, "junjo.store.revision.before"), 0),
            contract_int(get(attributes, "junjo.store.revision.after"), 0),
        );
        let (Some(sequence), Some(before_revision), Some(after_revision)) = facts else {
            diagnostics.push(EvidenceDiagnostic::new(
                "invalid_store_transition",
                "events",
                "Transition sequence and revisions must be non-negative contract integers.",
            ));
            replay_possible = false;
            continue;
        };
        let Some(event_id) = nonempty_text(get(attributes, "id")) else {
            diagnostics.push(EvidenceDiagnostic::new(
                "missing_transition_event_id",
                format!("events[{sequence}].id"),
                "Event ID is absent or invalid.",
            ));
            replay_possible = false;
            continue;
        };
        let Some(action) = nonempty_text(get(attributes, "junjo.store.action")) else {
            diagnostics.push(EvidenceDiagnostic::new(
                "missing_transition_action",
                format!("events[{sequence}].junjo.store.action"),
                "Store action is absent.",
            ));
            replay_possible = false;
            continue;
        };
        let patch =
            parse_required_payload_slot(attributes, "junjo.state_json_patch", &mut diagnostics);
        if patch.mode != start.mode || patch.policy != start.policy {
            diagnostics.push(EvidenceDiagnostic::new(
                "payload_policy_mismatch",
                format!("events[{sequence}].junjo.state_json_patch"),
                "Store transition evidence must use the start-state payload mode and policy.",
            ));
            replay_possible = false;
            policy_unavailable = false;
        }
        let before_state = if replay_possible {
            current_state.clone()
        } else {
            Json::Null
        };
        let mut after_state = Json::Null;
        if current_revision.is_some_and(|current| before_revision != current) {
            diagnostics.push(EvidenceDiagnostic::new(
                "revision_discontinuity",
                format!("events[{sequence}]"),
                "Revision-before does not match the preceding revision.",
            ));
            replay_possible = false;
        }
        let valid_revision_step =
            after_revision == before_revision || after_revision == before_revision + 1;
        if !valid_revision_step {
            diagnostics.push(EvidenceDiagnostic::new(
                "revision_discontinuity",
                format!("events[{sequence}]"),
                "Revision-after must stay equal or increment by one.",
            ));
            replay_possible = false;
        }
        match patch.value.as_array() {
            Some(operations) if replay_possible && patch.mode.is_inline() => {
                match apply_patch(&current_state, operations) {
                    Ok(patched) => {
                        after_state = patched.clone();
                        current_state = patched;
                    }
                    Err(error) => {
                        diagnostics.push(EvidenceDiagnostic::new(
                            "patch_replay_mismatch",
                            format!("events[{sequence}]"),
                            format!("Patch replay failed: {error}."),
                        ));
                        replay_possible = false;
                    }
                }
            }
            _ if inline_replay => replay_possible = false,
            _ => {}
        }
        current_revision = Some(after_revision);
        if !valid_revision_step {
            continue;
        }
        transitions.push(StoreTransition {
            sequence,
            revision_before: before_revision,
            revision_after: after_revision,
            span_id: span_id.to_string(),
            event_id: event_id.to_string(),
            action: action.to_string(),
            patch,
            before: before_state,
            after: after_state,
        });
    }

    let terminal_revision_matches = match current_revision {
        Some(current) => values_equal(&Json::from(current), revision_end),
        None => revision_end.is_null(),
    };
    if !terminal_revision_matches {
        diagnostics.push(EvidenceDiagnostic::new(
            "terminal_revision_mismatch",
            fact_key("revision.end"),
            "Terminal revision does not match the transition chain.",
        ));
        replay_possible = false;
    }
    if inline_replay && !values_equal(&current_state, &end.value) {
        diagnostics.push(EvidenceDiagnostic::new(
            "patch_replay_mismatch",
            boundary.state_end_root,
            "Replayed state does not exactly match emitted end state.",
        ));
        replay_possible = false;
    }

    let replay_verified = replay_possible && diagnostics.is_empty();
    if reconstructable_claimed == Some(true) && !replay_verified {
        diagnostics.push(EvidenceDiagnostic::new(
            "reconstructable_claim_mismatch",
            fact_key("reconstructable"),
            "Producer claimed reconstructability but independent replay failed.",
        ));
    }

    let (reconstruction_status, reconstruction_reason) = if replay_verified {
        (ReconstructionStatus::Verified, None)
    } else if policy_unavailable && diagnostics.is_empty() {
        (
            ReconstructionStatus::PolicyUnavailable,
            Some("payload_policy".to_string()),
        )
    } else {
        let reason = diagnostics
            .first()
            .map_or("replay_unavailable", |diagnostic| diagnostic.code.as_str());
        (ReconstructionStatus::Failed, Some(reason.to_string()))
    };

    StoreReconstructionResult {
        detail: StoreDetail {
            available: true,
            store_id: Some(store_id.to_string()),
            sequence_start: contract_int(sequence_start, 0),
            sequence_end: contract_int(sequence_end, 0),
            revision_start: contract_int(revision_start, 0),
            revision_end: contract_int(revision_end, 0),
            transition_count: contract_int(transition_count, 0).unwrap_or(0),
            reconstructable_claimed: reconstructable_claimed.unwrap_or(false),
            reconstructable: replay_verified,
            reconstruction_status,
            reconstruction_reason,
            start: Some(start),
            end: Some(end),
            transitions,
        },
        diagnostics,
        replay_verified,
    }
}

/// Carrier spans by the Store ID their `set_state` events name, each list in
/// trace order.
pub type StoreSpanIndex<'a> = HashMap<&'a str, Vec<&'a JsonObject>>;

/// The Store ID a `set_state` event names. Anything but non-empty text names
/// no Store.
fn event_store_id(event: &Json) -> Option<&str> {
    let event = event.as_object()?;
    let attributes = get(event, "attributes").as_object()?;
    let is_set_state = get(event, "name").as_str() == Some("set_state");
    let store_id = nonempty_text(get(attributes, "junjo.store.id"))?;
    is_set_state.then_some(store_id)
}

/// Index carrier spans once for traces containing multiple Store borrowers.
pub fn index_store_spans<'a>(spans: &[&'a JsonObject]) -> StoreSpanIndex<'a> {
    let mut index = StoreSpanIndex::new();
    for &span in spans {
        let Json::Array(events) = get(span, "events_json") else {
            continue;
        };
        // A span is listed once under each Store it carries events for.
        let store_ids: HashSet<&str> = events.iter().filter_map(event_store_id).collect();
        for store_id in store_ids {
            index.entry(store_id).or_default().push(span);
        }
    }
    index
}

/// Select same-trace Store carriers without inventing execution ownership.
///
/// The owner comes first, then every other span the index lists for the
/// Store ID. A carrier must itself declare the active contract. One that does
/// not is left out and diagnosed, so its events cannot be replayed as
/// evidence.
///
/// The owner is recognized among the carriers only as the same reference the
/// index holds. Pass that reference, or the owner's events are read twice.
pub fn store_evidence_spans<'a>(
    owner_span: &'a JsonObject,
    store_id: &Json,
    index: &StoreSpanIndex<'a>,
) -> (Vec<&'a JsonObject>, Vec<EvidenceDiagnostic>) {
    let mut selected = vec![owner_span];
    let mut diagnostics = Vec::new();
    let Some(carriers) = store_id.as_str().and_then(|store_id| index.get(store_id)) else {
        return (selected, diagnostics);
    };
    for &span in carriers {
        if std::ptr::eq(span, owner_span) {
            continue;
        }
        let version = get(attributes(span), "junjo.telemetry.contract_version");
        if !is_active_contract_version(version) {
            let code = if version.is_null() {
                "missing_contract_version"
            } else {
                "unsupported_contract"
            };
            diagnostics.push(EvidenceDiagnostic::new(
                code,
                span_evidence_path(span, "junjo.telemetry.contract_version", None),
                "Store event evidence requires the active telemetry contract version.",
            ));
            continue;
        }
        selected.push(span);
    }
    (selected, diagnostics)
}
