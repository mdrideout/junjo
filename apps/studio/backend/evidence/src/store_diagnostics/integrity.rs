//! Generic OTLP evidence-integrity assembly for semantic diagnostics.

use crate::json::{Json, JsonObject, get};
use crate::store_diagnostics::schemas::{
    EvidenceDiagnostic, EvidenceIntegrity, EvidenceLossCounts,
};
use crate::telemetry_contract::{MAX_IJSON_INTEGER, contract_int, is_uint64_decimal};

/// Return one verdict after validating all preserved OTLP loss evidence.
///
/// `diagnostics` holds what the caller already found. Problems with the loss
/// evidence itself are added after them.
pub fn assemble_evidence_integrity(
    spans: &[&JsonObject],
    mut diagnostics: Vec<EvidenceDiagnostic>,
) -> EvidenceIntegrity {
    let mut totals = EvidenceLossCounts::default();
    for (span_index, span) in spans.iter().enumerate() {
        let span_counters: [(&str, &mut i64); 4] = [
            (
                "resource_dropped_attributes_count",
                &mut totals.resource_dropped_attributes,
            ),
            (
                "dropped_attributes_count",
                &mut totals.span_dropped_attributes,
            ),
            ("dropped_events_count", &mut totals.span_dropped_events),
            ("dropped_links_count", &mut totals.span_dropped_links),
        ];
        for (raw_key, total) in span_counters {
            let path = format!("spans[{span_index}].{raw_key}");
            let Some(value) = span.get(raw_key) else {
                diagnostics.push(EvidenceDiagnostic::new(
                    "missing_loss_counter",
                    path,
                    "Required OTLP loss counter is absent.",
                ));
                continue;
            };
            if let Err(message) = add_loss(
                total,
                value,
                "OTLP loss counter is invalid.",
                "Aggregated OTLP loss counter exceeds the portable integer domain.",
            ) {
                diagnostics.push(EvidenceDiagnostic::new(
                    "invalid_loss_counter",
                    path,
                    message,
                ));
            }
        }

        let Json::Array(events) = get(span, "events_json") else {
            diagnostics.push(EvidenceDiagnostic::new(
                "missing_loss_counter",
                format!("spans[{span_index}].events_json"),
                "Required event evidence is absent.",
            ));
            continue;
        };
        for (event_index, event) in events.iter().enumerate() {
            let path = format!("spans[{span_index}].events[{event_index}]");
            let Json::Object(event) = event else {
                diagnostics.push(EvidenceDiagnostic::new(
                    "missing_loss_counter",
                    path,
                    "Required event evidence is absent.",
                ));
                continue;
            };
            if !is_uint64_decimal(get(event, "timeUnixNano")) {
                diagnostics.push(EvidenceDiagnostic::new(
                    "invalid_event_timestamp",
                    format!("{path}.timeUnixNano"),
                    "Event timestamp must be exact canonical uint64 decimal text.",
                ));
            }
            let Some(value) = event.get("droppedAttributesCount") else {
                diagnostics.push(EvidenceDiagnostic::new(
                    "missing_loss_counter",
                    path,
                    "Required event loss counter is absent.",
                ));
                continue;
            };
            if let Err(message) = add_loss(
                &mut totals.event_dropped_attributes,
                value,
                "Event loss counter is invalid.",
                "Aggregated event loss counter exceeds the portable integer domain.",
            ) {
                diagnostics.push(EvidenceDiagnostic::new(
                    "invalid_loss_counter",
                    path,
                    message,
                ));
            }
        }
    }
    EvidenceIntegrity::new(diagnostics, totals)
}

/// Add one counter to its total, keeping the total a contract integer.
fn add_loss<'a>(
    total: &mut i64,
    value: &Json,
    invalid: &'a str,
    overflow: &'a str,
) -> Result<(), &'a str> {
    let value = contract_int(value, 0).ok_or(invalid)?;
    if *total > MAX_IJSON_INTEGER - value {
        return Err(overflow);
    }
    *total += value;
    Ok(())
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use crate::store_diagnostics::schemas::IntegrityStatus;

    fn span(overrides: Json) -> JsonObject {
        let mut span = json!({
            "resource_dropped_attributes_count": 0,
            "dropped_attributes_count": 0,
            "dropped_events_count": 0,
            "dropped_links_count": 0,
            "events_json": [],
        });
        for (key, value) in overrides.as_object().unwrap() {
            if value.is_null() {
                span.as_object_mut().unwrap().remove(key);
            } else {
                span[key] = value.clone();
            }
        }
        span.as_object().unwrap().clone()
    }

    fn codes(integrity: &EvidenceIntegrity) -> Vec<&str> {
        integrity
            .diagnostics
            .iter()
            .map(|item| item.code.as_str())
            .collect()
    }

    #[test]
    fn clean_evidence_is_complete() {
        let span = span(json!({}));
        let integrity = assemble_evidence_integrity(&[&span], Vec::new());
        assert_eq!(integrity.status, IntegrityStatus::Complete);
        assert_eq!(integrity.loss_counts, EvidenceLossCounts::default());
    }

    #[test]
    fn recorded_loss_alone_makes_evidence_partial() {
        let first = span(json!({
            "dropped_attributes_count": 2,
            "events_json": [{"timeUnixNano": "1", "droppedAttributesCount": 3}],
        }));
        let second =
            span(json!({"dropped_links_count": 1, "resource_dropped_attributes_count": 4}));
        let integrity = assemble_evidence_integrity(&[&first, &second], Vec::new());
        assert_eq!(integrity.status, IntegrityStatus::Partial);
        assert!(integrity.diagnostics.is_empty());
        assert_eq!(integrity.loss_counts.span_dropped_attributes, 2);
        assert_eq!(integrity.loss_counts.span_dropped_links, 1);
        assert_eq!(integrity.loss_counts.resource_dropped_attributes, 4);
        assert_eq!(integrity.loss_counts.event_dropped_attributes, 3);
    }

    #[test]
    fn caller_diagnostics_come_first_and_make_evidence_partial() {
        let span = span(json!({"dropped_events_count": null}));
        let earlier = EvidenceDiagnostic::new("earlier", "path", "Found before.");
        let integrity = assemble_evidence_integrity(&[&span], vec![earlier]);
        assert_eq!(integrity.status, IntegrityStatus::Partial);
        assert_eq!(codes(&integrity), ["earlier", "missing_loss_counter"]);
        assert_eq!(
            integrity.diagnostics[1].path,
            "spans[0].dropped_events_count"
        );
    }

    #[test]
    fn invalid_counters_are_diagnosed_and_not_counted() {
        let span = span(json!({
            "dropped_attributes_count": true,
            "dropped_links_count": -1,
            "events_json": [
                "not an event",
                {"timeUnixNano": 1, "droppedAttributesCount": 1},
                {"timeUnixNano": "2"},
                {"timeUnixNano": "3", "droppedAttributesCount": 1.0},
            ],
        }));
        let integrity = assemble_evidence_integrity(&[&span], Vec::new());
        assert_eq!(
            codes(&integrity),
            [
                "invalid_loss_counter",
                "invalid_loss_counter",
                "missing_loss_counter",
                "invalid_event_timestamp",
                "missing_loss_counter",
                "invalid_loss_counter",
            ]
        );
        assert_eq!(integrity.loss_counts.event_dropped_attributes, 1);
        assert_eq!(integrity.loss_counts.span_dropped_attributes, 0);
    }

    #[test]
    fn missing_event_evidence_is_diagnosed() {
        let span = span(json!({"events_json": null}));
        let integrity = assemble_evidence_integrity(&[&span], Vec::new());
        assert_eq!(codes(&integrity), ["missing_loss_counter"]);
        assert_eq!(integrity.diagnostics[0].path, "spans[0].events_json");
    }

    #[test]
    fn totals_stay_inside_the_portable_integer_domain() {
        let first = span(json!({"dropped_attributes_count": MAX_IJSON_INTEGER}));
        let second = span(json!({"dropped_attributes_count": 1}));
        let integrity = assemble_evidence_integrity(&[&first, &second], Vec::new());
        assert_eq!(codes(&integrity), ["invalid_loss_counter"]);
        assert_eq!(
            integrity.loss_counts.span_dropped_attributes,
            MAX_IJSON_INTEGER
        );
    }
}
