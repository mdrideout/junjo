//! Span classification for the metadata index.
//!
//! One rule decides whether a span is an LLM, Workflow, or Agent span, and
//! which execution it owns. The indexer and the hot-tier LLM check share it.

use std::borrow::Cow;
use std::fmt;

use serde::Deserialize;
use serde::de::{Deserializer, IgnoredAny, MapAccess, SeqAccess, Visitor};

/// What the metadata index needs to know about one span's attributes.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct SpanClassification<'a> {
    pub is_llm: bool,
    pub is_workflow: bool,
    pub is_agent: bool,
    /// The type and the runtime identity of the Workflow, Subflow, or Agent
    /// execution this span owns.
    pub executable: Option<(Cow<'a, str>, Cow<'a, str>)>,
}

/// The span types that own an execution.
const EXECUTABLE_SPAN_TYPES: [&str; 3] = ["workflow", "subflow", "agent"];

/// The five attributes that classification reads. Every other attribute is
/// skipped without being materialized.
#[derive(Deserialize)]
struct ClassificationAttributes<'a> {
    #[serde(
        rename = "openinference.span.kind",
        default,
        borrow,
        deserialize_with = "text_or_nothing"
    )]
    openinference_span_kind: Option<Cow<'a, str>>,
    #[serde(
        rename = "gen_ai.provider.name",
        default,
        borrow,
        deserialize_with = "text_or_nothing"
    )]
    gen_ai_provider_name: Option<Cow<'a, str>>,
    #[serde(
        rename = "gen_ai.operation.name",
        default,
        borrow,
        deserialize_with = "text_or_nothing"
    )]
    gen_ai_operation_name: Option<Cow<'a, str>>,
    #[serde(
        rename = "junjo.span_type",
        default,
        borrow,
        deserialize_with = "text_or_nothing"
    )]
    junjo_span_type: Option<Cow<'a, str>>,
    #[serde(
        rename = "junjo.executable_runtime_id",
        default,
        borrow,
        deserialize_with = "text_or_nothing"
    )]
    junjo_executable_runtime_id: Option<Cow<'a, str>>,
}

/// Classify one span from its stored attributes JSON.
///
/// A span is an LLM span when it uses the OpenInference `LLM` kind, or names
/// a GenAI provider or operation with a non-empty string. Attributes that are
/// not a JSON object classify as nothing.
pub fn classify_attributes(attributes_json: &str) -> SpanClassification<'_> {
    // Only a JSON object carries attributes. Serde would otherwise accept an
    // array as positional fields.
    if !attributes_json.trim_start().starts_with('{') {
        return SpanClassification::default();
    }
    let Ok(attributes) = serde_json::from_str::<ClassificationAttributes<'_>>(attributes_json)
    else {
        return SpanClassification::default();
    };
    let is_non_empty =
        |value: &Option<Cow<'_, str>>| value.as_deref().is_some_and(|v| !v.is_empty());
    let span_type = attributes.junjo_span_type.as_deref();
    SpanClassification {
        is_llm: attributes.openinference_span_kind.as_deref() == Some("LLM")
            || is_non_empty(&attributes.gen_ai_provider_name)
            || is_non_empty(&attributes.gen_ai_operation_name),
        is_workflow: span_type == Some("workflow"),
        is_agent: span_type == Some("agent"),
        executable: match (
            attributes.junjo_span_type,
            attributes.junjo_executable_runtime_id,
        ) {
            (Some(span_type), Some(runtime_id))
                if EXECUTABLE_SPAN_TYPES.contains(&&*span_type) && !runtime_id.is_empty() =>
            {
                Some((span_type, runtime_id))
            }
            _ => None,
        },
    }
}

/// Deserialize a string, or nothing for any other JSON value.
fn text_or_nothing<'de, D>(deserializer: D) -> Result<Option<Cow<'de, str>>, D::Error>
where
    D: Deserializer<'de>,
{
    struct TextVisitor;

    impl<'de> Visitor<'de> for TextVisitor {
        type Value = Option<Cow<'de, str>>;

        fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
            formatter.write_str("any JSON value")
        }

        fn visit_borrowed_str<E>(self, value: &'de str) -> Result<Self::Value, E> {
            Ok(Some(Cow::Borrowed(value)))
        }

        fn visit_str<E>(self, value: &str) -> Result<Self::Value, E> {
            Ok(Some(Cow::Owned(value.to_owned())))
        }

        fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
            Ok(Some(Cow::Owned(value)))
        }

        fn visit_bool<E>(self, _: bool) -> Result<Self::Value, E> {
            Ok(None)
        }

        fn visit_i64<E>(self, _: i64) -> Result<Self::Value, E> {
            Ok(None)
        }

        fn visit_u64<E>(self, _: u64) -> Result<Self::Value, E> {
            Ok(None)
        }

        fn visit_f64<E>(self, _: f64) -> Result<Self::Value, E> {
            Ok(None)
        }

        fn visit_unit<E>(self) -> Result<Self::Value, E> {
            Ok(None)
        }

        fn visit_seq<A: SeqAccess<'de>>(self, mut sequence: A) -> Result<Self::Value, A::Error> {
            while sequence.next_element::<IgnoredAny>()?.is_some() {}
            Ok(None)
        }

        fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
            while map.next_entry::<IgnoredAny, IgnoredAny>()?.is_some() {}
            Ok(None)
        }
    }

    deserializer.deserialize_any(TextVisitor)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn classify(json: &str) -> (bool, bool, bool) {
        let classification = classify_attributes(json);
        (
            classification.is_llm,
            classification.is_workflow,
            classification.is_agent,
        )
    }

    #[test]
    fn openinference_and_genai_spans_are_llm_spans() {
        assert_eq!(
            classify(r#"{"openinference.span.kind":"LLM"}"#),
            (true, false, false)
        );
        assert_eq!(
            classify(r#"{"gen_ai.provider.name":"xai"}"#),
            (true, false, false)
        );
        assert_eq!(
            classify(r#"{"gen_ai.operation.name":"chat"}"#),
            (true, false, false)
        );
    }

    #[test]
    fn other_openinference_kinds_and_empty_genai_values_are_not_llm_spans() {
        assert_eq!(
            classify(r#"{"openinference.span.kind":"CHAIN"}"#),
            (false, false, false)
        );
        assert_eq!(
            classify(r#"{"gen_ai.provider.name":""}"#),
            (false, false, false)
        );
        assert_eq!(
            classify(r#"{"gen_ai.operation.name":7}"#),
            (false, false, false)
        );
        assert_eq!(
            classify(r#"{"gen_ai.provider.name":["xai"]}"#),
            (false, false, false)
        );
        assert_eq!(
            classify(r#"{"gen_ai.provider.name":{"name":"xai"}}"#),
            (false, false, false)
        );
        assert_eq!(
            classify(r#"{"gen_ai.provider.name":null}"#),
            (false, false, false)
        );
    }

    #[test]
    fn junjo_span_types_classify_workflow_and_agent_spans() {
        assert_eq!(
            classify(r#"{"junjo.span_type":"workflow"}"#),
            (false, true, false)
        );
        assert_eq!(
            classify(r#"{"junjo.span_type":"agent"}"#),
            (false, false, true)
        );
        assert_eq!(
            classify(r#"{"junjo.span_type":"node"}"#),
            (false, false, false)
        );
        assert_eq!(
            classify(r#"{"junjo.span_type":"subflow"}"#),
            (false, false, false)
        );
    }

    #[test]
    fn a_workflow_subflow_or_agent_span_with_a_runtime_identity_owns_an_execution() {
        let executable = |json: &str| {
            classify_attributes(json)
                .executable
                .map(|(span_type, runtime_id)| (span_type.into_owned(), runtime_id.into_owned()))
        };
        for span_type in ["workflow", "subflow", "agent"] {
            let json = format!(
                r#"{{"junjo.executable_runtime_id":"run-1","junjo.span_type":"{span_type}"}}"#
            );
            assert_eq!(
                executable(&json),
                Some((span_type.to_string(), "run-1".to_string()))
            );
        }
        // An identity with an escape is read as its text.
        assert_eq!(
            executable(r#"{"junjo.span_type":"agent","junjo.executable_runtime_id":"a\"b"}"#),
            Some(("agent".to_string(), "a\"b".to_string()))
        );
        for json in [
            r#"{"junjo.span_type":"node","junjo.executable_runtime_id":"run-1"}"#,
            r#"{"junjo.span_type":"workflow"}"#,
            r#"{"junjo.span_type":"workflow","junjo.executable_runtime_id":""}"#,
            r#"{"junjo.span_type":"workflow","junjo.executable_runtime_id":7}"#,
            r#"{"junjo.executable_runtime_id":"run-1"}"#,
        ] {
            assert_eq!(executable(json), None, "{json}");
        }
    }

    #[test]
    fn unrelated_payload_escapes_and_unicode_do_not_affect_classification() {
        let json = r#"{"input":"Synthetic request: 日本語 \"quoted\"","model":"synthetic","nested":{"a":[1,2,{"b":null}]},"junjo.span_type":"agent","gen_ai.operation.name":"chat"}"#;
        assert_eq!(classify(json), (true, false, true));
    }

    #[test]
    fn invalid_or_non_object_attributes_classify_as_nothing() {
        assert_eq!(classify(""), (false, false, false));
        assert_eq!(classify("not json"), (false, false, false));
        assert_eq!(classify("[]"), (false, false, false));
        assert_eq!(
            classify(r#"["LLM","xai","chat","agent"]"#),
            (false, false, false)
        );
        assert_eq!(classify("null"), (false, false, false));
        assert_eq!(
            classify(r#"{"junjo.span_type":"workflow""#),
            (false, false, false)
        );
    }
}
