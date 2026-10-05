//! Span timestamps as the semantic API reads and writes them.

use std::fmt::Write as _;

use chrono::{DateTime, FixedOffset, NaiveDateTime, Timelike};
use serde::{Serialize, Serializer};

/// An instant with its original offset, at microsecond resolution.
///
/// Equality and ordering compare the instant, not the offset.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Timestamp(DateTime<FixedOffset>);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TimestampError {
    Invalid,
    /// A date and time with no offset names no instant.
    MissingOffset,
}

impl Timestamp {
    /// Parse ISO 8601 text that carries an offset.
    pub fn parse(text: &str) -> Result<Self, TimestampError> {
        match DateTime::parse_from_rfc3339(text) {
            Ok(parsed) => {
                // Finer digits are dropped, never rounded.
                let microseconds = parsed.nanosecond() / 1_000 * 1_000;
                parsed
                    .with_nanosecond(microseconds)
                    .map(Self)
                    .ok_or(TimestampError::Invalid)
            }
            Err(_) if is_naive(text) => Err(TimestampError::MissingOffset),
            Err(_) => Err(TimestampError::Invalid),
        }
    }

    /// Whole microseconds from the Unix epoch to this instant.
    pub fn unix_microseconds(&self) -> i64 {
        self.0.timestamp_micros()
    }

    /// Whole microseconds from `earlier` to this instant.
    pub fn microseconds_since(&self, earlier: &Self) -> i64 {
        // Both sides hold whole microseconds, and the calendar range of a
        // parsed timestamp keeps the difference far inside 64 bits.
        (self.0 - earlier.0).num_microseconds().unwrap_or(i64::MAX)
    }
}

fn is_naive(text: &str) -> bool {
    ["%Y-%m-%dT%H:%M:%S%.f", "%Y-%m-%d %H:%M:%S%.f"]
        .iter()
        .any(|format| NaiveDateTime::parse_from_str(text, format).is_ok())
}

impl std::fmt::Display for Timestamp {
    /// UTC is written as `Z`, and the fraction only when it is not zero.
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let mut text = self.0.format("%Y-%m-%dT%H:%M:%S").to_string();
        let microseconds = self.0.nanosecond() / 1_000;
        if microseconds != 0 {
            write!(text, ".{microseconds:06}")?;
        }
        if self.0.offset().local_minus_utc() == 0 {
            text.push('Z');
        } else {
            write!(text, "{}", self.0.format("%:z"))?;
        }
        formatter.write_str(&text)
    }
}

impl Serialize for Timestamp {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.collect_str(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn utc_is_written_as_z_and_the_fraction_only_when_present() {
        let whole = Timestamp::parse("2026-07-13T12:00:00.000000+00:00").unwrap();
        assert_eq!(whole.to_string(), "2026-07-13T12:00:00Z");
        let fraction = Timestamp::parse("2026-07-13T12:00:00.000500+00:00").unwrap();
        assert_eq!(fraction.to_string(), "2026-07-13T12:00:00.000500Z");
        let zulu = Timestamp::parse("2026-07-13T12:00:00Z").unwrap();
        assert_eq!(zulu.to_string(), "2026-07-13T12:00:00Z");
    }

    #[test]
    fn other_offsets_are_kept() {
        let offset = Timestamp::parse("2026-07-13T17:30:00.25+05:30").unwrap();
        assert_eq!(offset.to_string(), "2026-07-13T17:30:00.250000+05:30");
    }

    #[test]
    fn digits_past_microseconds_are_dropped() {
        let precise = Timestamp::parse("2026-07-13T12:00:00.123456789Z").unwrap();
        assert_eq!(precise.to_string(), "2026-07-13T12:00:00.123456Z");
    }

    #[test]
    fn instants_compare_across_offsets() {
        let utc = Timestamp::parse("2026-07-13T12:00:00Z").unwrap();
        let shifted = Timestamp::parse("2026-07-13T14:00:00+02:00").unwrap();
        let later = Timestamp::parse("2026-07-13T12:00:00.000001Z").unwrap();
        assert_eq!(utc, shifted);
        assert!(later > utc);
        assert_eq!(later.microseconds_since(&shifted), 1);
        let epoch = Timestamp::parse("1970-01-01T00:00:00Z").unwrap();
        assert_eq!(later.unix_microseconds(), later.microseconds_since(&epoch));
        assert_eq!(utc.microseconds_since(&later), -1);
    }

    #[test]
    fn text_without_an_offset_is_distinguished_from_invalid_text() {
        assert_eq!(
            Timestamp::parse("2026-07-13T12:00:00"),
            Err(TimestampError::MissingOffset)
        );
        assert_eq!(
            Timestamp::parse("2026-07-13 12:00:00.5"),
            Err(TimestampError::MissingOffset)
        );
        assert_eq!(Timestamp::parse("yesterday"), Err(TimestampError::Invalid));
        assert_eq!(Timestamp::parse(""), Err(TimestampError::Invalid));
    }
}
