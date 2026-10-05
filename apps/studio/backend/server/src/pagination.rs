//! Bounded result limits and opaque keyset cursors for list endpoints.

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use serde::Deserialize;
use serde_json::{Map, Value, json};

use crate::error::ApiError;
use crate::timestamps::UtcSeconds;

/// A result limit from 1 to `MAX`. `DEFAULT` applies when the caller sends
/// none.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(try_from = "u32")]
pub struct Limit<const MAX: u32, const DEFAULT: u32>(u32);

impl<const MAX: u32, const DEFAULT: u32> Limit<MAX, DEFAULT> {
    pub fn get(self) -> u32 {
        self.0
    }
}

impl<const MAX: u32, const DEFAULT: u32> Default for Limit<MAX, DEFAULT> {
    fn default() -> Self {
        Self(DEFAULT)
    }
}

impl<const MAX: u32, const DEFAULT: u32> TryFrom<u32> for Limit<MAX, DEFAULT> {
    type Error = String;

    fn try_from(value: u32) -> Result<Self, Self::Error> {
        if (1..=MAX).contains(&value) {
            Ok(Self(value))
        } else {
            Err(format!("limit must be between 1 and {MAX}"))
        }
    }
}

pub const MAX_PAGE_SIZE: u32 = 100;
pub const DEFAULT_PAGE_SIZE: u32 = 50;

/// The page size of a paginated listing.
pub type PageLimit = Limit<MAX_PAGE_SIZE, DEFAULT_PAGE_SIZE>;

pub const MAX_CURSOR_BYTES: usize = 1_024;

/// A cursor as a caller sends it: opaque text of 1 to 1,024 bytes.
#[derive(Debug, Clone, Deserialize)]
#[serde(try_from = "String")]
pub struct Cursor(String);

impl TryFrom<String> for Cursor {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if value.is_empty() {
            return Err("cursor must not be empty".to_string());
        }
        if value.len() > MAX_CURSOR_BYTES {
            return Err(format!(
                "cursor must be at most {MAX_CURSOR_BYTES} UTF-8 bytes"
            ));
        }
        Ok(Self(value))
    }
}

/// A cursor that does not name a position in the listing it was sent to.
#[derive(Debug, PartialEq, Eq)]
pub struct InvalidCursor;

impl From<InvalidCursor> for ApiError {
    fn from(_: InvalidCursor) -> Self {
        ApiError::validation("Invalid pagination cursor")
    }
}

/// Encode a cursor's members as opaque text. The members name the listing
/// they belong to, so a cursor from one listing is refused by another.
pub fn encode_cursor(members: &Value) -> String {
    URL_SAFE_NO_PAD.encode(members.to_string())
}

/// Decode the members of a cursor a caller sent.
pub fn decode_cursor(cursor: &Cursor) -> Result<Map<String, Value>, InvalidCursor> {
    let bytes = URL_SAFE_NO_PAD
        .decode(&cursor.0)
        .map_err(|_| InvalidCursor)?;
    match serde_json::from_slice(&bytes) {
        Ok(Value::Object(members)) => Ok(members),
        _ => Err(InvalidCursor),
    }
}

/// Whether a cursor's members belong to the listing named `kind`.
pub fn is_cursor_kind(members: &Map<String, Value>, kind: &str) -> bool {
    members.get("v") == Some(&json!(1)) && members.get("kind") == Some(&json!(kind))
}

/// A record's place in a listing ordered newest first, then by identifier.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TimePosition {
    pub created_at: UtcSeconds,
    pub id: String,
}

/// The cursor that continues a newest-first listing after `position`.
pub fn encode_time_cursor(kind: &str, position: &TimePosition) -> String {
    encode_cursor(&json!({
        "v": 1,
        "kind": kind,
        "created_at": position.created_at.format(),
        "id": position.id,
    }))
}

pub fn decode_time_cursor(kind: &str, cursor: &Cursor) -> Result<TimePosition, InvalidCursor> {
    let members = decode_cursor(cursor)?;
    if !is_cursor_kind(&members, kind) {
        return Err(InvalidCursor);
    }
    let created_at = members
        .get("created_at")
        .and_then(Value::as_str)
        .and_then(UtcSeconds::parse)
        .ok_or(InvalidCursor)?;
    let id = members
        .get("id")
        .and_then(Value::as_str)
        .filter(|id| !id.is_empty())
        .ok_or(InvalidCursor)?;
    Ok(TimePosition {
        created_at,
        id: id.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cursor(text: &str) -> Cursor {
        Cursor::try_from(text.to_string()).unwrap()
    }

    #[test]
    fn a_limit_is_bounded_and_has_a_default() {
        assert_eq!(PageLimit::default().get(), 50);
        assert_eq!(PageLimit::try_from(1).unwrap().get(), 1);
        assert_eq!(PageLimit::try_from(100).unwrap().get(), 100);
        assert!(PageLimit::try_from(0).is_err());
        assert!(PageLimit::try_from(101).is_err());
    }

    #[test]
    fn a_cursor_is_one_to_1024_bytes() {
        assert!(Cursor::try_from(String::new()).is_err());
        assert!(Cursor::try_from("a".repeat(MAX_CURSOR_BYTES)).is_ok());
        assert!(Cursor::try_from("a".repeat(MAX_CURSOR_BYTES + 1)).is_err());
    }

    #[test]
    fn a_time_cursor_round_trips_within_its_listing() {
        let position = TimePosition {
            created_at: UtcSeconds::from_unix(1_736_937_000),
            id: "record-1".to_string(),
        };
        let encoded = encode_time_cursor("runs", &position);
        assert!(!encoded.contains('='));
        assert_eq!(decode_time_cursor("runs", &cursor(&encoded)), Ok(position));
        // A cursor from another listing is refused.
        assert_eq!(
            decode_time_cursor("datasets", &cursor(&encoded)),
            Err(InvalidCursor)
        );
    }

    #[test]
    fn a_malformed_cursor_is_refused() {
        let encoded = |members: Value| cursor(&encode_cursor(&members));
        let valid =
            json!({"v": 1, "kind": "runs", "created_at": "2025-01-15T10:30:00Z", "id": "a"});
        assert!(decode_time_cursor("runs", &encoded(valid.clone())).is_ok());

        for (member, value) in [
            ("v", json!(2)),
            ("kind", json!("other")),
            ("created_at", json!("2025-01-15 10:30:00")),
            ("created_at", json!(5)),
            ("id", json!("")),
            ("id", json!(7)),
        ] {
            let mut members = valid.clone();
            members[member] = value.clone();
            assert_eq!(
                decode_time_cursor("runs", &encoded(members)),
                Err(InvalidCursor),
                "{member} = {value}"
            );
        }
        assert_eq!(
            decode_time_cursor("runs", &cursor("____")),
            Err(InvalidCursor)
        );
        assert_eq!(
            decode_time_cursor("runs", &cursor("not base64!")),
            Err(InvalidCursor)
        );
        assert_eq!(
            decode_time_cursor("runs", &encoded(json!([1, 2]))),
            Err(InvalidCursor)
        );
    }
}
