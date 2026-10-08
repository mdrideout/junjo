//! Portable scalar rules shared by every semantic telemetry consumer.

use crate::json::{Json, JsonObject, get};

pub const ACTIVE_TELEMETRY_CONTRACT_VERSION: i64 = 3;
/// The largest integer every JSON consumer can represent exactly.
pub const MAX_IJSON_INTEGER: i64 = 9_007_199_254_740_991;

/// A contract integer: a JSON integer, never a boolean or a float, inside the
/// interoperable range and at or above `minimum`.
pub fn contract_int(value: &Json, minimum: i64) -> Option<i64> {
    let number = value.as_number()?;
    if number.is_f64() {
        return None;
    }
    let integer = number.as_i64()?;
    (minimum..=MAX_IJSON_INTEGER)
        .contains(&integer)
        .then_some(integer)
}

/// Text of any length. Rust strings are always Unicode scalar text, so the
/// contract's "portable text" rule reduces to "is a string".
pub fn text(value: &Json) -> Option<&str> {
    value.as_str()
}

/// Text that is present and not empty.
pub fn nonempty_text(value: &Json) -> Option<&str> {
    value.as_str().filter(|text| !text.is_empty())
}

/// Text that is exactly one of the allowed values.
pub fn portable_enum<'a>(value: &'a Json, allowed: &[&str]) -> Option<&'a str> {
    nonempty_text(value).filter(|text| allowed.contains(text))
}

/// One exact lowercase hexadecimal transport identity.
pub fn is_lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
}

/// A value that is an exact lowercase hexadecimal identity of `length`.
pub fn lower_hex(value: &Json, length: usize) -> Option<&str> {
    value.as_str().filter(|text| is_lower_hex(text, length))
}

/// Exactly the active semantic telemetry contract version.
pub fn is_active_contract_version(value: &Json) -> bool {
    contract_int(value, i64::MIN) == Some(ACTIVE_TELEMETRY_CONTRACT_VERSION)
}

/// Canonical decimal text for an unsigned 64-bit scalar.
pub fn is_uint64_decimal(value: &Json) -> bool {
    let Some(text) = value.as_str() else {
        return false;
    };
    let canonical = text == "0"
        || (!text.is_empty()
            && !text.starts_with('0')
            && text.bytes().all(|byte| byte.is_ascii_digit()));
    canonical && text.parse::<u64>().is_ok()
}

/// A diagnostic path for one span that never interpolates an untrusted
/// identity.
pub fn span_evidence_path(span: &JsonObject, suffix: &str, index: Option<usize>) -> String {
    let base = match (lower_hex(get(span, "span_id"), 16), index) {
        (Some(span_id), _) => format!("span[{span_id}]"),
        (None, Some(index)) => format!("spans[{index}]"),
        (None, None) => "span[unidentified]".to_string(),
    };
    if suffix.is_empty() {
        base
    } else {
        format!("{base}.{suffix}")
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn contract_integers_exclude_booleans_floats_and_unsafe_values() {
        assert_eq!(contract_int(&json!(0), 0), Some(0));
        assert_eq!(
            contract_int(&json!(MAX_IJSON_INTEGER), 0),
            Some(MAX_IJSON_INTEGER)
        );
        assert_eq!(contract_int(&json!(MAX_IJSON_INTEGER + 1), 0), None);
        assert_eq!(contract_int(&json!(-1), 0), None);
        assert_eq!(contract_int(&json!(0), 1), None);
        assert_eq!(contract_int(&json!(1.0), 0), None);
        assert_eq!(contract_int(&json!(true), 0), None);
        assert_eq!(contract_int(&json!("1"), 0), None);
        assert_eq!(contract_int(&json!(null), 0), None);
        assert_eq!(contract_int(&json!(u64::MAX), 0), None);
    }

    #[test]
    fn enumerations_match_exact_text_only() {
        assert_eq!(
            portable_enum(&json!("full"), &["full", "redacted"]),
            Some("full")
        );
        assert_eq!(portable_enum(&json!("Full"), &["full"]), None);
        assert_eq!(portable_enum(&json!(""), &[""]), None);
        assert_eq!(portable_enum(&json!(1), &["1"]), None);
    }

    #[test]
    fn hexadecimal_identities_are_exact() {
        assert!(is_lower_hex("0123456789abcdef", 16));
        assert!(!is_lower_hex("0123456789ABCDEF", 16));
        assert!(!is_lower_hex("0123456789abcde", 16));
        assert!(!is_lower_hex("0123456789abcdef\n", 16));
        assert_eq!(lower_hex(&json!(1), 1), None);
    }

    #[test]
    fn only_the_active_contract_version_is_recognized() {
        assert!(is_active_contract_version(&json!(3)));
        assert!(!is_active_contract_version(&json!(3.0)));
        assert!(!is_active_contract_version(&json!("3")));
        assert!(!is_active_contract_version(&json!(2)));
        assert!(!is_active_contract_version(&json!(null)));
    }

    #[test]
    fn uint64_decimal_text_is_canonical_and_in_range() {
        assert!(is_uint64_decimal(&json!("0")));
        assert!(is_uint64_decimal(&json!("18446744073709551615")));
        assert!(!is_uint64_decimal(&json!("18446744073709551616")));
        assert!(!is_uint64_decimal(&json!("01")));
        assert!(!is_uint64_decimal(&json!("")));
        assert!(!is_uint64_decimal(&json!("-1")));
        assert!(!is_uint64_decimal(&json!("1.0")));
        assert!(!is_uint64_decimal(&json!(1)));
    }

    #[test]
    fn span_paths_never_carry_an_invalid_identity() {
        let valid = json!({"span_id": "0123456789abcdef"});
        let invalid = json!({"span_id": "not-a-span"});
        assert_eq!(
            span_evidence_path(valid.as_object().unwrap(), "trace_id", Some(3)),
            "span[0123456789abcdef].trace_id"
        );
        assert_eq!(
            span_evidence_path(invalid.as_object().unwrap(), "events_json", Some(3)),
            "spans[3].events_json"
        );
        assert_eq!(
            span_evidence_path(invalid.as_object().unwrap(), "", None),
            "span[unidentified]"
        );
    }
}
