//! The two timestamp formats the backend stores and serializes.

use chrono::{DateTime, NaiveDateTime, Utc};
use rusqlite::types::{FromSql, FromSqlError, FromSqlResult, ToSql, ToSqlOutput, ValueRef};
use serde::{Deserialize, Serialize, Serializer};

const STORED_FORMAT: &str = "%Y-%m-%dT%H:%M:%SZ";

/// A UTC timestamp at whole-second precision.
///
/// This type owns the format used for application records in `junjo.db` and
/// in API responses: `YYYY-MM-DDTHH:MM:SSZ`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct UtcSeconds(i64);

impl UtcSeconds {
    pub fn now() -> Self {
        Self(Utc::now().timestamp())
    }

    #[cfg(test)]
    pub fn from_unix(seconds: i64) -> Self {
        Self(seconds)
    }

    pub fn as_unix(self) -> i64 {
        self.0
    }

    /// The timestamp this many seconds later.
    pub fn plus_seconds(self, seconds: i64) -> Self {
        Self(self.0 + seconds)
    }

    pub fn format(self) -> String {
        DateTime::<Utc>::from_timestamp(self.0, 0)
            .unwrap_or(DateTime::<Utc>::UNIX_EPOCH)
            .format(STORED_FORMAT)
            .to_string()
    }

    pub fn parse(text: &str) -> Option<Self> {
        NaiveDateTime::parse_from_str(text, STORED_FORMAT)
            .ok()
            .map(|naive| Self(naive.and_utc().timestamp()))
    }
}

impl Serialize for UtcSeconds {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(&self.format())
    }
}

impl ToSql for UtcSeconds {
    fn to_sql(&self) -> rusqlite::Result<ToSqlOutput<'_>> {
        Ok(ToSqlOutput::from(self.format()))
    }
}

impl FromSql for UtcSeconds {
    fn column_result(value: ValueRef<'_>) -> FromSqlResult<Self> {
        let text = value.as_str()?;
        Self::parse(text)
            .ok_or_else(|| FromSqlError::Other(format!("invalid stored timestamp {text:?}").into()))
    }
}

/// A timestamp a caller sends: RFC 3339 with an explicit offset, kept at the
/// precision sent.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Deserialize)]
#[serde(try_from = "String")]
pub struct RequestTimestamp(DateTime<Utc>);

impl TryFrom<String> for RequestTimestamp {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        DateTime::parse_from_rfc3339(&value)
            .map(|timestamp| Self(timestamp.with_timezone(&Utc)))
            .map_err(|_| {
                "timestamp must be RFC 3339 with an offset, such as 2026-01-15T10:30:00Z"
                    .to_string()
            })
    }
}

impl RequestTimestamp {
    pub fn is_in_the_future(self) -> bool {
        self.0 > Utc::now()
    }

    /// The stored form: whole seconds, with any fraction dropped.
    pub fn to_seconds(self) -> UtcSeconds {
        UtcSeconds(self.0.timestamp())
    }
}

/// Format a span timestamp in nanoseconds since the Unix epoch as the raw
/// span API does: microsecond precision with an explicit `+00:00` offset.
/// A missing or zero timestamp is the empty string.
pub fn format_span_timestamp(nanoseconds: Option<i64>) -> String {
    let Some(nanoseconds) = nanoseconds.filter(|value| *value != 0) else {
        return String::new();
    };
    let seconds = nanoseconds.div_euclid(1_000_000_000);
    let microseconds = nanoseconds.rem_euclid(1_000_000_000) / 1_000;
    match DateTime::<Utc>::from_timestamp(seconds, (microseconds * 1_000) as u32) {
        Some(timestamp) => timestamp.format("%Y-%m-%dT%H:%M:%S%.6f+00:00").to_string(),
        None => String::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stored_format_round_trips_at_whole_seconds() {
        let timestamp = UtcSeconds::from_unix(1_736_937_000);
        assert_eq!(timestamp.format(), "2025-01-15T10:30:00Z");
        assert_eq!(UtcSeconds::parse("2025-01-15T10:30:00Z"), Some(timestamp));
        assert_eq!(UtcSeconds::parse("2025-01-15 10:30:00"), None);
    }

    #[test]
    fn a_later_timestamp_is_counted_in_seconds() {
        let timestamp = UtcSeconds::from_unix(1_736_937_000);
        assert_eq!(timestamp.plus_seconds(900).format(), "2025-01-15T10:45:00Z");
        assert!(timestamp.plus_seconds(1) > timestamp);
    }

    #[test]
    fn a_request_timestamp_needs_an_offset_and_is_stored_in_utc_seconds() {
        let parse = |text: &str| RequestTimestamp::try_from(text.to_string());
        assert_eq!(
            parse("2025-01-15T12:30:00.987654+02:00")
                .unwrap()
                .to_seconds(),
            UtcSeconds::from_unix(1_736_937_000)
        );
        assert_eq!(
            parse("2025-01-15T10:30:00Z").unwrap().to_seconds().format(),
            "2025-01-15T10:30:00Z"
        );
        assert!(parse("2025-01-15T10:30:00").is_err());
        assert!(parse("tomorrow").is_err());
        assert!(!parse("2025-01-15T10:30:00Z").unwrap().is_in_the_future());
        assert!(parse("9999-01-01T00:00:00Z").unwrap().is_in_the_future());
    }

    #[test]
    fn span_timestamps_floor_to_microseconds() {
        assert_eq!(
            format_span_timestamp(Some(1_736_937_000_123_456_789)),
            "2025-01-15T10:30:00.123456+00:00"
        );
        assert_eq!(
            format_span_timestamp(Some(1_736_937_000_000_000_000)),
            "2025-01-15T10:30:00.000000+00:00"
        );
        assert_eq!(format_span_timestamp(Some(0)), "");
        assert_eq!(format_span_timestamp(None), "");
    }

    #[test]
    fn span_timestamps_before_the_epoch_floor_toward_negative_infinity() {
        // One nanosecond before the epoch is the last microsecond of 1969.
        assert_eq!(
            format_span_timestamp(Some(-1)),
            "1969-12-31T23:59:59.999999+00:00"
        );
    }
}
