//! The JSON value model evidence logic works over.
//!
//! Span evidence is untrusted, loosely typed JSON. These helpers give it the
//! value semantics the telemetry producers use, so a comparison made here
//! agrees with one made where the evidence was emitted.

pub type Json = serde_json::Value;
pub type JsonObject = serde_json::Map<String, Json>;

static NULL: Json = Json::Null;

/// Read one member. An absent member reads as null, so "absent" and "null"
/// are one case for every value check. Use `contains_key` where presence
/// itself is the evidence.
pub fn get<'a>(object: &'a JsonObject, key: &str) -> &'a Json {
    object.get(key).unwrap_or(&NULL)
}

/// Read one member of a value that may not be an object.
pub fn member<'a>(value: &'a Json, key: &str) -> &'a Json {
    value.as_object().map_or(&NULL, |object| get(object, key))
}

/// Compare two values the way the producers' JSON model does.
///
/// Numbers compare by numeric value, so `1` equals `1.0`. Booleans compare
/// equal to `0` and `1`: producers compute Store patches with this rule, so a
/// replay must use it too or it would report differences they never emitted.
/// Object member order is not significant.
pub fn values_equal(left: &Json, right: &Json) -> bool {
    match (left, right) {
        (Json::Null, Json::Null) => true,
        (Json::String(left), Json::String(right)) => left == right,
        (Json::Array(left), Json::Array(right)) => {
            left.len() == right.len()
                && left
                    .iter()
                    .zip(right)
                    .all(|(left, right)| values_equal(left, right))
        }
        (Json::Object(left), Json::Object(right)) => {
            left.len() == right.len()
                && left.iter().all(|(key, left)| {
                    right
                        .get(key)
                        .is_some_and(|right| values_equal(left, right))
                })
        }
        _ => match (Numeric::of(left), Numeric::of(right)) {
            (Some(left), Some(right)) => left == right,
            _ => false,
        },
    }
}

/// A number or boolean as an exactly comparable quantity.
#[derive(Debug, Clone, Copy)]
enum Numeric {
    Integer(i128),
    Float(f64),
}

impl Numeric {
    fn of(value: &Json) -> Option<Self> {
        match value {
            Json::Bool(value) => Some(Self::Integer(i128::from(*value))),
            Json::Number(number) => {
                if let Some(integer) = number.as_i64() {
                    Some(Self::Integer(i128::from(integer)))
                } else if let Some(integer) = number.as_u64() {
                    Some(Self::Integer(i128::from(integer)))
                } else {
                    number.as_f64().map(Self::Float)
                }
            }
            _ => None,
        }
    }
}

impl PartialEq for Numeric {
    fn eq(&self, other: &Self) -> bool {
        match (*self, *other) {
            (Self::Integer(left), Self::Integer(right)) => left == right,
            (Self::Float(left), Self::Float(right)) => left == right,
            (Self::Integer(integer), Self::Float(float))
            | (Self::Float(float), Self::Integer(integer)) => {
                // Exact: an integer equals a float only when the float is
                // that whole number. Every stored integer fits in 65 bits, so
                // the conversion below cannot lose the comparison.
                float.fract() == 0.0 && float.abs() < 1e30 && float as i128 == integer
            }
        }
    }
}

/// Render an observed value for a diagnostic message.
pub fn display(value: &Json) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "an unrenderable value".to_string())
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn an_absent_member_reads_as_null() {
        let object = json!({"present": 1, "explicit": null});
        let object = object.as_object().unwrap();
        assert_eq!(get(object, "present"), &json!(1));
        assert_eq!(get(object, "explicit"), &Json::Null);
        assert_eq!(get(object, "absent"), &Json::Null);
        assert_eq!(member(&json!("text"), "anything"), &Json::Null);
    }

    #[test]
    fn numbers_compare_by_value() {
        assert!(values_equal(&json!(1), &json!(1.0)));
        assert!(values_equal(
            &json!({"a": [1, 2.0]}),
            &json!({"a": [1.0, 2]})
        ));
        assert!(!values_equal(&json!(1), &json!(1.5)));
        assert!(!values_equal(
            &json!(9007199254740993_i64),
            &json!(9007199254740992.0)
        ));
        assert!(values_equal(&json!(u64::MAX), &json!(u64::MAX)));
    }

    #[test]
    fn booleans_compare_equal_to_zero_and_one() {
        assert!(values_equal(&json!(true), &json!(1)));
        assert!(values_equal(&json!(false), &json!(0.0)));
        assert!(!values_equal(&json!(true), &json!(2)));
        assert!(!values_equal(&json!(true), &json!("true")));
    }

    #[test]
    fn member_order_is_not_significant() {
        assert!(values_equal(
            &json!({"a": 1, "b": 2}),
            &json!({"b": 2, "a": 1})
        ));
        assert!(!values_equal(&json!({"a": 1}), &json!({"a": 1, "b": null})));
        assert!(!values_equal(&json!([1, 2]), &json!([2, 1])));
    }

    #[test]
    fn different_kinds_are_never_equal() {
        assert!(!values_equal(&json!(null), &json!(0)));
        assert!(!values_equal(&json!("1"), &json!(1)));
        assert!(!values_equal(&json!([]), &json!({})));
    }
}
