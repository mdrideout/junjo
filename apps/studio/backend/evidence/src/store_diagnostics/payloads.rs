//! Strict parsing of telemetry payload-slot evidence.
//!
//! Payload content is JSON text inside a span attribute. The contract accepts
//! only the interoperable I-JSON domain: unique object names, safe integers,
//! finite numbers, Unicode scalar text, and bounded nesting. General-purpose
//! JSON parsers silently accept or silently repair each of those, so this
//! module owns one explicit scanner.

use std::collections::HashSet;

use crate::json::{Json, JsonObject, display, get};
use crate::store_diagnostics::schemas::{EvidenceDiagnostic, PayloadEvidence, PayloadMode};
use crate::telemetry_contract::{MAX_IJSON_INTEGER, nonempty_text, portable_enum};

/// The root is depth 0. Object names, object values, and array elements are
/// children.
pub const MAX_JSON_NESTING_DEPTH: usize = 128;

/// Where the scanner stops descending. Anything this deep is far past the
/// contract bound, and stopping keeps hostile input from exhausting the
/// stack.
const SCANNER_NESTING_LIMIT: usize = 1024;

/// Why a payload string is not usable contract JSON.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum JsonDecodeError {
    /// Not JSON at all, including the non-standard `NaN` and `Infinity`.
    Invalid,
    /// One object repeats a member name.
    DuplicateName,
    /// An unsafe integer, a non-finite number, or text that is not Unicode
    /// scalar values.
    NonPortable,
    /// Nesting beyond the contract bound.
    TooDeep,
}

/// Decode strict finite JSON without silently collapsing duplicate names.
pub fn decode_json_value(raw: &str) -> Result<Json, JsonDecodeError> {
    let node = Scanner::new(raw).document()?;
    validate_portable(&node)?;
    Ok(node.into_json())
}

/// Text as the scanner found it. A lone surrogate escape cannot be stored in
/// a Rust string, so such text keeps its code points only to compare names.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
enum Text {
    Portable(String),
    NonPortable(Vec<u32>),
}

impl Text {
    fn push_str(&mut self, run: &str) {
        match self {
            Self::Portable(text) => text.push_str(run),
            Self::NonPortable(points) => points.extend(run.chars().map(u32::from)),
        }
    }

    fn push_char(&mut self, character: char) {
        match self {
            Self::Portable(text) => text.push(character),
            Self::NonPortable(points) => points.push(u32::from(character)),
        }
    }

    fn push_lone_surrogate(&mut self, unit: u32) {
        if let Self::Portable(text) = self {
            *self = Self::NonPortable(text.chars().map(u32::from).collect());
        }
        if let Self::NonPortable(points) = self {
            points.push(unit);
        }
    }
}

#[derive(Debug)]
enum Node {
    Null,
    Bool(bool),
    /// An integer literal. `None` when it does not fit in 64 bits.
    Integer(Option<i64>),
    Float(f64),
    Text(Text),
    Array(Vec<Node>),
    Object(Vec<(Text, Node)>),
}

impl Node {
    /// Convert a validated tree. Validation guarantees every case below.
    fn into_json(self) -> Json {
        match self {
            Self::Null => Json::Null,
            Self::Bool(value) => Json::Bool(value),
            Self::Integer(value) => Json::from(value.unwrap_or_default()),
            Self::Float(value) => {
                serde_json::Number::from_f64(value).map_or(Json::Null, Json::Number)
            }
            Self::Text(text) => Json::String(portable(text)),
            Self::Array(items) => Json::Array(items.into_iter().map(Self::into_json).collect()),
            Self::Object(members) => Json::Object(
                members
                    .into_iter()
                    .map(|(name, value)| (portable(name), value.into_json()))
                    .collect(),
            ),
        }
    }
}

fn portable(text: Text) -> String {
    match text {
        Text::Portable(text) => text,
        Text::NonPortable(_) => String::new(),
    }
}

struct Scanner<'a> {
    input: &'a str,
    bytes: &'a [u8],
    position: usize,
}

impl<'a> Scanner<'a> {
    fn new(input: &'a str) -> Self {
        Self {
            input,
            bytes: input.as_bytes(),
            position: 0,
        }
    }

    fn document(mut self) -> Result<Node, JsonDecodeError> {
        self.skip_whitespace();
        let value = self.value(0)?;
        self.skip_whitespace();
        if self.position == self.bytes.len() {
            Ok(value)
        } else {
            Err(JsonDecodeError::Invalid)
        }
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.position).copied()
    }

    fn skip_whitespace(&mut self) {
        while let Some(b' ' | b'\t' | b'\n' | b'\r') = self.peek() {
            self.position += 1;
        }
    }

    fn value(&mut self, depth: usize) -> Result<Node, JsonDecodeError> {
        match self.peek() {
            Some(b'{') => self.object(depth),
            Some(b'[') => self.array(depth),
            Some(b'"') => Ok(Node::Text(self.string()?)),
            Some(b't') => self.literal("true", Node::Bool(true)),
            Some(b'f') => self.literal("false", Node::Bool(false)),
            Some(b'n') => self.literal("null", Node::Null),
            Some(b'-' | b'0'..=b'9') => self.number(),
            _ => Err(JsonDecodeError::Invalid),
        }
    }

    fn literal(&mut self, text: &str, node: Node) -> Result<Node, JsonDecodeError> {
        if self.bytes[self.position..].starts_with(text.as_bytes()) {
            self.position += text.len();
            Ok(node)
        } else {
            Err(JsonDecodeError::Invalid)
        }
    }

    fn object(&mut self, depth: usize) -> Result<Node, JsonDecodeError> {
        if depth >= SCANNER_NESTING_LIMIT {
            return Err(JsonDecodeError::TooDeep);
        }
        self.position += 1;
        let mut members: Vec<(Text, Node)> = Vec::new();
        self.skip_whitespace();
        if self.peek() == Some(b'}') {
            self.position += 1;
            return Ok(Node::Object(members));
        }
        loop {
            self.skip_whitespace();
            if self.peek() != Some(b'"') {
                return Err(JsonDecodeError::Invalid);
            }
            let name = self.string()?;
            self.skip_whitespace();
            if self.peek() != Some(b':') {
                return Err(JsonDecodeError::Invalid);
            }
            self.position += 1;
            self.skip_whitespace();
            let value = self.value(depth + 1)?;
            members.push((name, value));
            self.skip_whitespace();
            match self.peek() {
                Some(b',') => self.position += 1,
                Some(b'}') => {
                    self.position += 1;
                    break;
                }
                _ => return Err(JsonDecodeError::Invalid),
            }
        }
        // A repeated name is reported when its object closes. A syntax error
        // earlier in the text is therefore reported first, and one later in
        // the text is not reached.
        let mut seen = HashSet::with_capacity(members.len());
        if members.iter().all(|(name, _)| seen.insert(name)) {
            Ok(Node::Object(members))
        } else {
            Err(JsonDecodeError::DuplicateName)
        }
    }

    fn array(&mut self, depth: usize) -> Result<Node, JsonDecodeError> {
        if depth >= SCANNER_NESTING_LIMIT {
            return Err(JsonDecodeError::TooDeep);
        }
        self.position += 1;
        let mut items = Vec::new();
        self.skip_whitespace();
        if self.peek() == Some(b']') {
            self.position += 1;
            return Ok(Node::Array(items));
        }
        loop {
            self.skip_whitespace();
            items.push(self.value(depth + 1)?);
            self.skip_whitespace();
            match self.peek() {
                Some(b',') => self.position += 1,
                Some(b']') => {
                    self.position += 1;
                    return Ok(Node::Array(items));
                }
                _ => return Err(JsonDecodeError::Invalid),
            }
        }
    }

    fn number(&mut self) -> Result<Node, JsonDecodeError> {
        let start = self.position;
        if self.peek() == Some(b'-') {
            self.position += 1;
        }
        match self.peek() {
            Some(b'0') => self.position += 1,
            Some(b'1'..=b'9') => self.skip_digits(),
            _ => return Err(JsonDecodeError::Invalid),
        }
        // A fraction or exponent belongs to the number only when complete.
        // Otherwise the number ends here and the caller rejects what follows.
        let mut is_float = false;
        if self.peek() == Some(b'.') && self.is_digit_at(self.position + 1) {
            is_float = true;
            self.position += 1;
            self.skip_digits();
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            let mut digits = self.position + 1;
            if matches!(self.bytes.get(digits), Some(b'+' | b'-')) {
                digits += 1;
            }
            if self.is_digit_at(digits) {
                is_float = true;
                self.position = digits;
                self.skip_digits();
            }
        }
        let literal = &self.input[start..self.position];
        if is_float {
            // Out-of-range literals parse to infinity and fail validation.
            literal
                .parse::<f64>()
                .map(Node::Float)
                .map_err(|_| JsonDecodeError::Invalid)
        } else {
            Ok(Node::Integer(literal.parse::<i64>().ok()))
        }
    }

    fn is_digit_at(&self, position: usize) -> bool {
        self.bytes.get(position).is_some_and(u8::is_ascii_digit)
    }

    fn skip_digits(&mut self) {
        while self.is_digit_at(self.position) {
            self.position += 1;
        }
    }

    fn string(&mut self) -> Result<Text, JsonDecodeError> {
        self.position += 1;
        let mut text = Text::Portable(String::new());
        loop {
            // Every stopping byte is ASCII, so the run ends on a character
            // boundary.
            let run_start = self.position;
            while let Some(byte) = self.peek() {
                if byte == b'"' || byte == b'\\' || byte < 0x20 {
                    break;
                }
                self.position += 1;
            }
            text.push_str(&self.input[run_start..self.position]);
            match self.peek() {
                Some(b'"') => {
                    self.position += 1;
                    return Ok(text);
                }
                Some(b'\\') => {
                    self.position += 1;
                    self.escape(&mut text)?;
                }
                // An unescaped control character, or the text ended.
                _ => return Err(JsonDecodeError::Invalid),
            }
        }
    }

    fn escape(&mut self, text: &mut Text) -> Result<(), JsonDecodeError> {
        let escaped = self.peek().ok_or(JsonDecodeError::Invalid)?;
        self.position += 1;
        let character = match escaped {
            b'"' => '"',
            b'\\' => '\\',
            b'/' => '/',
            b'b' => '\u{0008}',
            b'f' => '\u{000C}',
            b'n' => '\n',
            b'r' => '\r',
            b't' => '\t',
            b'u' => return self.unicode_escape(text),
            _ => return Err(JsonDecodeError::Invalid),
        };
        text.push_char(character);
        Ok(())
    }

    fn unicode_escape(&mut self, text: &mut Text) -> Result<(), JsonDecodeError> {
        let unit = self.hex_unit()?;
        if (0xD800..=0xDBFF).contains(&unit) && self.bytes[self.position..].starts_with(b"\\u") {
            let after_high = self.position;
            self.position += 2;
            let low = self.hex_unit()?;
            if (0xDC00..=0xDFFF).contains(&low) {
                let scalar = 0x10000 + ((unit - 0xD800) << 10) + (low - 0xDC00);
                text.push_char(char::from_u32(scalar).ok_or(JsonDecodeError::Invalid)?);
                return Ok(());
            }
            // Not a pair. The second escape is read again by itself.
            self.position = after_high;
        }
        match char::from_u32(unit) {
            Some(character) => text.push_char(character),
            None => text.push_lone_surrogate(unit),
        }
        Ok(())
    }

    fn hex_unit(&mut self) -> Result<u32, JsonDecodeError> {
        let digits = self
            .bytes
            .get(self.position..self.position + 4)
            .ok_or(JsonDecodeError::Invalid)?;
        let mut unit = 0;
        for digit in digits {
            let value = char::from(*digit)
                .to_digit(16)
                .ok_or(JsonDecodeError::Invalid)?;
            unit = unit * 16 + value;
        }
        self.position += 4;
        Ok(unit)
    }
}

/// Check the decoded tree against the interoperable domain.
///
/// The walk is depth-first from the last member backwards. When a payload
/// breaks more than one rule, that order decides which one is reported, and
/// it is kept so the reported code is stable across consumers.
fn validate_portable(root: &Node) -> Result<(), JsonDecodeError> {
    enum Item<'a> {
        Value(&'a Node),
        Name(&'a Text),
    }

    fn text_is_portable(text: &Text) -> Result<(), JsonDecodeError> {
        match text {
            Text::Portable(_) => Ok(()),
            Text::NonPortable(_) => Err(JsonDecodeError::NonPortable),
        }
    }

    let mut pending = vec![(Item::Value(root), 0usize)];
    while let Some((item, depth)) = pending.pop() {
        if depth > MAX_JSON_NESTING_DEPTH {
            return Err(JsonDecodeError::TooDeep);
        }
        match item {
            Item::Name(name) => text_is_portable(name)?,
            Item::Value(Node::Null | Node::Bool(_)) => {}
            Item::Value(Node::Integer(value)) => {
                let safe = value
                    .is_some_and(|value| (-MAX_IJSON_INTEGER..=MAX_IJSON_INTEGER).contains(&value));
                if !safe {
                    return Err(JsonDecodeError::NonPortable);
                }
            }
            Item::Value(Node::Float(value)) => {
                if !value.is_finite() {
                    return Err(JsonDecodeError::NonPortable);
                }
            }
            Item::Value(Node::Text(text)) => text_is_portable(text)?,
            Item::Value(Node::Array(items)) => {
                pending.extend(items.iter().map(|item| (Item::Value(item), depth + 1)));
            }
            Item::Value(Node::Object(members)) => {
                for (name, value) in members {
                    pending.push((Item::Name(name), depth + 1));
                    pending.push((Item::Value(value), depth + 1));
                }
            }
        }
    }
    Ok(())
}

/// Whether any content, mode, policy, or reference member of a slot exists.
pub fn payload_slot_present(attributes: &JsonObject, root: &str) -> bool {
    attributes.contains_key(root)
        || ["mode", "policy", "reference"]
            .iter()
            .any(|member| attributes.contains_key(&format!("{root}.{member}")))
}

/// Represent absent required evidence without inventing contract content.
fn missing_payload(
    root: &str,
    code: &str,
    reason: String,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> PayloadEvidence {
    let diagnostic = EvidenceDiagnostic::new(code, root, reason);
    let evidence = PayloadEvidence {
        mode: PayloadMode::Missing,
        policy: None,
        value: Json::Null,
        reference: None,
        reason: Some(diagnostic.message.clone()),
    };
    diagnostics.push(diagnostic);
    evidence
}

/// Parse a slot that must exist. An absent slot becomes missing evidence
/// with a diagnostic.
pub fn parse_required_payload_slot(
    attributes: &JsonObject,
    root: &str,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> PayloadEvidence {
    parse_payload_slot(attributes, root, diagnostics).unwrap_or_else(|| {
        missing_payload(
            root,
            "required_payload_slot_missing",
            format!("Required payload slot '{root}' is absent."),
            diagnostics,
        )
    })
}

/// Parse one payload slot while retaining malformed evidence as diagnostics.
///
/// Returns `None` only when no member of the slot exists at all.
pub fn parse_payload_slot(
    attributes: &JsonObject,
    root: &str,
    diagnostics: &mut Vec<EvidenceDiagnostic>,
) -> Option<PayloadEvidence> {
    let reference_key = format!("{root}.reference");
    let mode = get(attributes, &format!("{root}.mode"));
    let policy = get(attributes, &format!("{root}.policy"));
    let content_present = attributes.contains_key(root);
    let reference_present = attributes.contains_key(&reference_key);
    if mode.is_null() && policy.is_null() && !content_present && !reference_present {
        return None;
    }
    let mut invalid =
        |code: &str, reason: String| Some(missing_payload(root, code, reason, diagnostics));

    let Some(mode) = portable_enum(mode, &PayloadMode::EMITTED).and_then(PayloadMode::from_emitted)
    else {
        return invalid(
            "invalid_payload_slot",
            format!("Payload mode {} is invalid.", display(mode)),
        );
    };
    let Some(policy) = nonempty_text(policy) else {
        return invalid(
            "required_payload_slot_missing",
            "Payload policy is absent or invalid.".to_string(),
        );
    };

    let mut value = Json::Null;
    let mut reference = None;
    match mode {
        PayloadMode::Full | PayloadMode::Redacted => {
            let content = attributes.get(root).and_then(Json::as_str);
            let Some(content) = content.filter(|_| !reference_present) else {
                return invalid(
                    "invalid_payload_slot",
                    "Payload content/reference does not match mode.".to_string(),
                );
            };
            value = match decode_json_value(content) {
                Ok(value) => value,
                Err(JsonDecodeError::DuplicateName) => {
                    return invalid(
                        "duplicate_json_object_name",
                        "Payload JSON repeats an object name.".to_string(),
                    );
                }
                Err(JsonDecodeError::NonPortable) => {
                    return invalid(
                        "nonportable_json_value",
                        "Payload JSON is outside the I-JSON domain.".to_string(),
                    );
                }
                Err(JsonDecodeError::TooDeep) => {
                    return invalid(
                        "payload_nesting_too_deep",
                        format!(
                            "Payload JSON exceeds the maximum nesting depth of {MAX_JSON_NESTING_DEPTH}."
                        ),
                    );
                }
                Err(JsonDecodeError::Invalid) => {
                    return invalid(
                        "invalid_payload_json",
                        "Payload content is not valid JSON.".to_string(),
                    );
                }
            };
        }
        PayloadMode::Reference => {
            let raw_reference = nonempty_text(get(attributes, &reference_key));
            let Some(raw_reference) = raw_reference.filter(|_| !content_present) else {
                return invalid(
                    "invalid_payload_slot",
                    "Reference payload is invalid.".to_string(),
                );
            };
            reference = Some(raw_reference.to_string());
        }
        PayloadMode::Excluded | PayloadMode::Missing => {
            if content_present || reference_present {
                return invalid(
                    "invalid_payload_slot",
                    "Excluded payload unexpectedly has content.".to_string(),
                );
            }
        }
    }

    Some(PayloadEvidence {
        mode,
        policy: Some(policy.to_string()),
        value,
        reference,
        reason: None,
    })
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn attributes(value: Json) -> JsonObject {
        value.as_object().unwrap().clone()
    }

    fn parse(value: Json, root: &str) -> (Option<PayloadEvidence>, Vec<EvidenceDiagnostic>) {
        let mut diagnostics = Vec::new();
        let evidence = parse_payload_slot(&attributes(value), root, &mut diagnostics);
        (evidence, diagnostics)
    }

    fn only_code(diagnostics: &[EvidenceDiagnostic]) -> &str {
        assert_eq!(diagnostics.len(), 1, "{diagnostics:?}");
        &diagnostics[0].code
    }

    #[test]
    fn decodes_ordinary_json_and_keeps_member_order() {
        let value =
            decode_json_value(r#" {"b": [1, 2.5, -0, true, null], "a": "x\u00e9\ud83d\ude00"} "#)
                .unwrap();
        assert_eq!(value, json!({"b": [1, 2.5, 0, true, null], "a": "xé😀"}));
        let names: Vec<&String> = value.as_object().unwrap().keys().collect();
        assert_eq!(names, ["b", "a"]);
    }

    #[test]
    fn integers_and_floats_keep_their_kind() {
        let value = decode_json_value("[1, 1.0, 1e2, -3]").unwrap();
        let items = value.as_array().unwrap();
        assert!(items[0].is_i64());
        assert!(items[1].is_f64());
        assert!(items[2].is_f64());
        assert_eq!(items[3], json!(-3));
    }

    #[test]
    fn rejects_text_that_is_not_json() {
        for raw in [
            "",
            "   ",
            "{",
            "[1,]",
            "{\"a\":1,}",
            "{'a':1}",
            "01",
            "1.",
            "1e",
            "-",
            "+1",
            "NaN",
            "Infinity",
            "-Infinity",
            "nul",
            "\"unterminated",
            "\"bad \\x escape\"",
            "\"\\u12G4\"",
            "\"raw \u{0001} control\"",
            "1 2",
            "{\"a\" 1}",
            "\u{feff}1",
        ] {
            assert_eq!(
                decode_json_value(raw),
                Err(JsonDecodeError::Invalid),
                "{raw:?}"
            );
        }
    }

    #[test]
    fn rejects_duplicate_names_at_any_depth() {
        assert_eq!(
            decode_json_value(r#"{"a":1,"a":2}"#),
            Err(JsonDecodeError::DuplicateName)
        );
        assert_eq!(
            decode_json_value(r#"{"outer":[{"a":1,"b":2,"a":3}]}"#),
            Err(JsonDecodeError::DuplicateName)
        );
        // Escapes are compared after decoding.
        assert_eq!(
            decode_json_value(r#"{"a":1,"\u0061":2}"#),
            Err(JsonDecodeError::DuplicateName)
        );
    }

    #[test]
    fn a_duplicate_is_reported_when_its_object_closes() {
        // The inner object closes before the later syntax error is reached.
        assert_eq!(
            decode_json_value(r#"{"x":{"a":1,"a":2},"y":tru}"#),
            Err(JsonDecodeError::DuplicateName)
        );
        // The object never closes, so the syntax error is what is found.
        assert_eq!(
            decode_json_value(r#"{"a":1,"a":2,bad}"#),
            Err(JsonDecodeError::Invalid)
        );
    }

    #[test]
    fn rejects_values_outside_the_interoperable_domain() {
        for raw in [
            "9007199254740992",
            "-9007199254740992",
            "123456789012345678901234567890",
            "1e999",
            r#""\ud800""#,
            r#""\udc00\ud800""#,
            r#"{"\ud800":1}"#,
            r#"["ok", {"deep": "\ud83d"}]"#,
        ] {
            assert_eq!(
                decode_json_value(raw),
                Err(JsonDecodeError::NonPortable),
                "{raw}"
            );
        }
        assert_eq!(
            decode_json_value("9007199254740991").unwrap(),
            json!(MAX_IJSON_INTEGER)
        );
        assert_eq!(
            decode_json_value("-9007199254740991").unwrap(),
            json!(-MAX_IJSON_INTEGER)
        );
    }

    #[test]
    fn distinct_lone_surrogate_names_are_not_duplicates() {
        assert_eq!(
            decode_json_value(r#"{"\ud800":1,"\ud801":2}"#),
            Err(JsonDecodeError::NonPortable)
        );
        assert_eq!(
            decode_json_value(r#"{"\ud800":1,"\ud800":2}"#),
            Err(JsonDecodeError::DuplicateName)
        );
    }

    fn nested_arrays(depth: usize) -> String {
        format!("{}{}", "[".repeat(depth), "]".repeat(depth))
    }

    #[test]
    fn nesting_is_bounded_with_the_root_at_depth_zero() {
        // 129 arrays put the innermost array at depth 128.
        assert!(decode_json_value(&nested_arrays(MAX_JSON_NESTING_DEPTH + 1)).is_ok());
        assert_eq!(
            decode_json_value(&nested_arrays(MAX_JSON_NESTING_DEPTH + 2)),
            Err(JsonDecodeError::TooDeep)
        );
        assert_eq!(
            decode_json_value(&nested_arrays(100_000)),
            Err(JsonDecodeError::TooDeep)
        );
    }

    #[test]
    fn object_names_count_as_children() {
        let mut raw = String::new();
        for _ in 0..MAX_JSON_NESTING_DEPTH {
            raw.push_str("{\"k\":");
        }
        raw.push('1');
        raw.push_str(&"}".repeat(MAX_JSON_NESTING_DEPTH));
        assert!(decode_json_value(&raw).is_ok());
        let deeper = format!("{{\"k\":{raw}}}");
        assert_eq!(decode_json_value(&deeper), Err(JsonDecodeError::TooDeep));
    }

    #[test]
    fn the_last_member_decides_which_rule_is_reported() {
        let deep = nested_arrays(MAX_JSON_NESTING_DEPTH + 2);
        assert_eq!(
            decode_json_value(&format!(r#"{{"unsafe":9007199254740992,"deep":{deep}}}"#)),
            Err(JsonDecodeError::TooDeep)
        );
        assert_eq!(
            decode_json_value(&format!(r#"{{"deep":{deep},"unsafe":9007199254740992}}"#)),
            Err(JsonDecodeError::NonPortable)
        );
    }

    #[test]
    fn an_absent_slot_is_none_or_missing_evidence() {
        let (evidence, diagnostics) = parse(json!({}), "slot");
        assert_eq!(evidence, None);
        assert!(diagnostics.is_empty());

        let mut diagnostics = Vec::new();
        let evidence =
            parse_required_payload_slot(&attributes(json!({})), "slot", &mut diagnostics);
        assert_eq!(evidence.mode, PayloadMode::Missing);
        assert_eq!(
            evidence.reason.as_deref(),
            Some("Required payload slot 'slot' is absent.")
        );
        assert_eq!(only_code(&diagnostics), "required_payload_slot_missing");
        assert_eq!(diagnostics[0].path, "slot");
    }

    #[test]
    fn parses_each_emitted_mode() {
        let (evidence, diagnostics) = parse(
            json!({"slot": "{\"a\":1}", "slot.mode": "full", "slot.policy": "junjo.full.v1"}),
            "slot",
        );
        let evidence = evidence.unwrap();
        assert!(diagnostics.is_empty());
        assert_eq!(evidence.mode, PayloadMode::Full);
        assert_eq!(evidence.policy.as_deref(), Some("junjo.full.v1"));
        assert_eq!(evidence.value, json!({"a": 1}));

        let (evidence, diagnostics) = parse(
            json!({"slot.mode": "reference", "slot.policy": "p", "slot.reference": "urn:x"}),
            "slot",
        );
        assert!(diagnostics.is_empty());
        assert_eq!(evidence.unwrap().reference.as_deref(), Some("urn:x"));

        let (evidence, diagnostics) =
            parse(json!({"slot.mode": "excluded", "slot.policy": "p"}), "slot");
        assert!(diagnostics.is_empty());
        assert_eq!(evidence.unwrap().mode, PayloadMode::Excluded);
    }

    #[test]
    fn a_json_null_payload_is_emitted_evidence() {
        let (evidence, diagnostics) = parse(
            json!({"slot": "null", "slot.mode": "redacted", "slot.policy": "p"}),
            "slot",
        );
        let evidence = evidence.unwrap();
        assert!(diagnostics.is_empty());
        assert_eq!(evidence.mode, PayloadMode::Redacted);
        assert_eq!(evidence.value, Json::Null);
    }

    #[test]
    fn malformed_slots_become_missing_evidence_with_a_code() {
        let cases = [
            (
                json!({"slot.mode": "bogus", "slot.policy": "p"}),
                "invalid_payload_slot",
            ),
            (
                json!({"slot.mode": 1, "slot.policy": "p"}),
                "invalid_payload_slot",
            ),
            (json!({"slot.policy": "p"}), "invalid_payload_slot"),
            (
                json!({"slot.mode": "full"}),
                "required_payload_slot_missing",
            ),
            (
                json!({"slot.mode": "full", "slot.policy": ""}),
                "required_payload_slot_missing",
            ),
            (
                json!({"slot.mode": "full", "slot.policy": "p"}),
                "invalid_payload_slot",
            ),
            (
                json!({"slot": {"a": 1}, "slot.mode": "full", "slot.policy": "p"}),
                "invalid_payload_slot",
            ),
            (
                json!({"slot": "1", "slot.mode": "full", "slot.policy": "p", "slot.reference": "r"}),
                "invalid_payload_slot",
            ),
            (
                json!({"slot": "{", "slot.mode": "full", "slot.policy": "p"}),
                "invalid_payload_json",
            ),
            (
                json!({"slot": "{\"a\":1,\"a\":2}", "slot.mode": "full", "slot.policy": "p"}),
                "duplicate_json_object_name",
            ),
            (
                json!({"slot": "9007199254740992", "slot.mode": "full", "slot.policy": "p"}),
                "nonportable_json_value",
            ),
            (
                json!({"slot": nested_arrays(200), "slot.mode": "full", "slot.policy": "p"}),
                "payload_nesting_too_deep",
            ),
            (
                json!({"slot.mode": "reference", "slot.policy": "p"}),
                "invalid_payload_slot",
            ),
            (
                json!({"slot": "1", "slot.mode": "reference", "slot.policy": "p", "slot.reference": "r"}),
                "invalid_payload_slot",
            ),
            (
                json!({"slot": "1", "slot.mode": "excluded", "slot.policy": "p"}),
                "invalid_payload_slot",
            ),
            (
                json!({"slot.mode": "excluded", "slot.policy": "p", "slot.reference": "r"}),
                "invalid_payload_slot",
            ),
        ];
        for (input, expected) in cases {
            let (evidence, diagnostics) = parse(input.clone(), "slot");
            let evidence = evidence.unwrap();
            assert_eq!(evidence.mode, PayloadMode::Missing, "{input}");
            assert_eq!(evidence.policy, None);
            assert_eq!(evidence.reason.as_ref(), Some(&diagnostics[0].message));
            assert_eq!(only_code(&diagnostics), expected, "{input}");
        }
    }

    #[test]
    fn slot_presence_sees_every_member() {
        for key in ["slot", "slot.mode", "slot.policy", "slot.reference"] {
            assert!(payload_slot_present(
                &attributes(json!({key: null})),
                "slot"
            ));
        }
        assert!(!payload_slot_present(
            &attributes(json!({"slot.other": 1})),
            "slot"
        ));
    }
}
