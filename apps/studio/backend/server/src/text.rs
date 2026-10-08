//! Validated text a caller sends.

use serde::Deserialize;

/// Whether a character counts as whitespace around text a caller sends:
/// Unicode whitespace, and the four ASCII separator controls, U+001C to
/// U+001F.
fn is_whitespace(character: char) -> bool {
    character.is_whitespace() || matches!(character, '\u{1c}'..='\u{1f}')
}

/// Text without its surrounding whitespace.
pub fn trimmed(text: &str) -> &str {
    text.trim_matches(is_whitespace)
}

/// Text that is not empty.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(try_from = "String")]
pub struct NonEmptyText(String);

impl NonEmptyText {
    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub fn into_string(self) -> String {
        self.0
    }
}

impl TryFrom<String> for NonEmptyText {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if value.is_empty() {
            return Err("value must not be empty".to_string());
        }
        Ok(Self(value))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn surrounding_whitespace_includes_the_ascii_separator_controls() {
        assert_eq!(trimmed("  name\t\n"), "name");
        assert_eq!(trimmed("\u{a0}name\u{3000}"), "name");
        assert_eq!(trimmed("\u{1c}\u{1d}name\u{1e}\u{1f}"), "name");
        assert_eq!(trimmed("two words"), "two words");
        assert_eq!(trimmed(" \u{1f} "), "");
        // Other controls are content, not whitespace.
        assert_eq!(trimmed("\u{1b}name"), "\u{1b}name");
    }

    #[test]
    fn non_empty_text_has_at_least_one_character() {
        assert!(NonEmptyText::try_from(String::new()).is_err());
        assert_eq!(
            NonEmptyText::try_from(" ".to_string()).unwrap().as_str(),
            " "
        );
    }
}
