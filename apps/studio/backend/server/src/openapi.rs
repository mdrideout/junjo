//! The OpenAPI document Studio publishes.
//!
//! The document is generated from the Rust types and routes. It is then
//! rewritten into the JSON Schema encoding the Studio contract has always
//! used, so the frontend's mock generator and the SDK's contract test read it
//! unchanged:
//!
//! - a value that may be null is `anyOf` with the value first;
//! - a single-value enumeration is a `const`;
//! - integers carry no machine-width format;
//! - arbitrary JSON is the empty schema, not a named component.

use serde_json::{Map, Value, json};

/// Keywords that describe a value's type and constraints. In a nullable
/// schema they belong to the non-null branch.
const TYPE_KEYWORDS: [&str; 16] = [
    "type",
    "format",
    "enum",
    "const",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "items",
    "minItems",
    "maxItems",
    "properties",
    "additionalProperties",
];

/// Number formats that describe a Rust width, not a contract rule.
const WIDTH_FORMATS: [&str; 10] = [
    "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64", "float", "double",
];

/// The component the generator creates for `serde_json::Value`.
const ANY_JSON_REFERENCE: &str = "#/components/schemas/Value";

/// Render a generated document in the published encoding.
pub fn published(document: &utoipa::openapi::OpenApi) -> serde_json::Result<Value> {
    let mut document = serde_json::to_value(document)?;
    normalize(&mut document);
    if let Some(schemas) = document
        .pointer_mut("/components/schemas")
        .and_then(Value::as_object_mut)
    {
        schemas.shift_remove("Value");
    }
    Ok(document)
}

fn normalize(value: &mut Value) {
    match value {
        Value::Array(items) => items.iter_mut().for_each(normalize),
        Value::Object(schema) => {
            schema.values_mut().for_each(normalize);
            inline_any_json(schema);
            drop_width_format(schema);
            drop_text_property_names(schema);
            single_value_enum_to_const(schema);
            nullable_type_to_any_of(schema);
            nullable_one_of_to_any_of(schema);
        }
        _ => {}
    }
}

fn inline_any_json(schema: &mut Map<String, Value>) {
    if schema.get("$ref").and_then(Value::as_str) == Some(ANY_JSON_REFERENCE) {
        schema.shift_remove("$ref");
    }
}

fn drop_width_format(schema: &mut Map<String, Value>) {
    let is_width = schema
        .get("format")
        .and_then(Value::as_str)
        .is_some_and(|format| WIDTH_FORMATS.contains(&format));
    if is_width {
        schema.shift_remove("format");
    }
}

/// Every JSON object name is text, so saying so adds nothing.
fn drop_text_property_names(schema: &mut Map<String, Value>) {
    if schema.get("propertyNames") == Some(&json!({"type": "string"})) {
        schema.shift_remove("propertyNames");
    }
}

fn single_value_enum_to_const(schema: &mut Map<String, Value>) {
    let single = match schema.get("enum") {
        Some(Value::Array(values)) if values.len() == 1 => values[0].clone(),
        _ => return,
    };
    schema.shift_remove("enum");
    schema.insert("const".to_string(), single);
}

/// `{"type": ["string", "null"], ...}` becomes
/// `{"anyOf": [{"type": "string", ...}, {"type": "null"}]}`.
fn nullable_type_to_any_of(schema: &mut Map<String, Value>) {
    let Some(Value::Array(types)) = schema.get("type") else {
        return;
    };
    let value_types: Vec<Value> = types
        .iter()
        .filter(|kind| *kind != "null")
        .cloned()
        .collect();
    if value_types.len() != 1 || value_types.len() == types.len() {
        return;
    }
    let mut branch = Map::new();
    for keyword in TYPE_KEYWORDS {
        if let Some(value) = schema.shift_remove(keyword) {
            branch.insert(keyword.to_string(), value);
        }
    }
    branch.insert("type".to_string(), value_types[0].clone());
    let mut rewritten = Map::new();
    rewritten.insert(
        "anyOf".to_string(),
        Value::Array(vec![Value::Object(branch), json!({"type": "null"})]),
    );
    rewritten.append(schema);
    *schema = rewritten;
}

/// A reference that may be null is written with `anyOf`, value first.
fn nullable_one_of_to_any_of(schema: &mut Map<String, Value>) {
    let Some(Value::Array(branches)) = schema.get("oneOf") else {
        return;
    };
    let null_schema = json!({"type": "null"});
    if branches.len() != 2 || !branches.contains(&null_schema) {
        return;
    }
    let Some(value) = branches
        .iter()
        .find(|branch| **branch != null_schema)
        .cloned()
    else {
        return;
    };
    schema.shift_remove("oneOf");
    let mut rewritten = Map::new();
    rewritten.insert("anyOf".to_string(), Value::Array(vec![value, null_schema]));
    rewritten.append(schema);
    *schema = rewritten;
}

#[cfg(test)]
mod tests {
    use super::*;

    fn normalized(mut value: Value) -> Value {
        normalize(&mut value);
        value
    }

    #[test]
    fn a_nullable_value_becomes_any_of_with_the_value_first() {
        assert_eq!(
            normalized(json!({
                "type": ["string", "null"],
                "minLength": 1,
                "description": "kept outside",
            })),
            json!({
                "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
                "description": "kept outside",
            })
        );
        assert_eq!(
            normalized(
                json!({"oneOf": [{"type": "null"}, {"$ref": "#/components/schemas/Thing"}]})
            ),
            json!({"anyOf": [{"$ref": "#/components/schemas/Thing"}, {"type": "null"}]})
        );
    }

    #[test]
    fn a_real_union_is_left_alone() {
        let union = json!({"oneOf": [
            {"$ref": "#/components/schemas/A"},
            {"$ref": "#/components/schemas/B"},
        ]});
        assert_eq!(normalized(union.clone()), union);
        let three = json!({"oneOf": [{"type": "null"}, {"type": "string"}, {"type": "integer"}]});
        assert_eq!(normalized(three.clone()), three);
    }

    #[test]
    fn integers_lose_their_width_and_keep_their_bounds() {
        assert_eq!(
            normalized(json!({"type": "integer", "format": "int64", "minimum": 0})),
            json!({"type": "integer", "minimum": 0})
        );
        assert_eq!(
            normalized(json!({"type": ["integer", "null"], "format": "int64", "maximum": 5})),
            json!({"anyOf": [{"type": "integer", "maximum": 5}, {"type": "null"}]})
        );
        assert_eq!(
            normalized(json!({"type": "string", "format": "date-time"})),
            json!({"type": "string", "format": "date-time"})
        );
    }

    #[test]
    fn a_single_value_enumeration_is_a_constant() {
        assert_eq!(
            normalized(json!({"type": "string", "enum": ["agent"]})),
            json!({"type": "string", "const": "agent"})
        );
        let two = json!({"type": "string", "enum": ["workflow", "subflow"]});
        assert_eq!(normalized(two.clone()), two);
    }

    #[test]
    fn arbitrary_json_is_the_empty_schema() {
        assert_eq!(
            normalized(json!({"type": "array", "items": {"$ref": ANY_JSON_REFERENCE}})),
            json!({"type": "array", "items": {}})
        );
    }

    #[test]
    fn maps_do_not_restate_that_names_are_text() {
        assert_eq!(
            normalized(json!({
                "type": "object",
                "additionalProperties": {"type": "integer"},
                "propertyNames": {"type": "string"},
            })),
            json!({"type": "object", "additionalProperties": {"type": "integer"}})
        );
        let closed = json!({"type": "object", "propertyNames": {"enum": ["a", "b"]}});
        assert_eq!(normalized(closed.clone()), closed);
    }
}
