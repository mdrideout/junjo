//! Identifier and credential generation.

/// Alphabet for record identifiers and API-key secrets: URL- and CLI-safe.
const ALPHANUMERIC: [char; 62] = [
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i',
    'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', 'A', 'B',
    'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U',
    'V', 'W', 'X', 'Y', 'Z',
];

const RECORD_ID_LENGTH: usize = 22;
const API_KEY_PREFIX: &str = "jtel_";
const API_KEY_SECRET_LENGTH: usize = 64;
const ACCESS_TOKEN_PREFIX: &str = "jcli_";
const ACCESS_TOKEN_SECRET_LENGTH: usize = 64;
const DEVICE_CODE_PREFIX: &str = "jdev_";
const DEVICE_CODE_SECRET_LENGTH: usize = 64;

/// Alphabet for CLI sign-in user codes, which a person reads in a terminal
/// and confirms in a browser: twenty consonants. Without vowels a code spells
/// no word.
const USER_CODE_ALPHABET: [char; 20] = [
    'B', 'C', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'V', 'W', 'X',
    'Z',
];
const USER_CODE_LENGTH: usize = 8;

/// A 22-character record identifier.
pub fn generate_id() -> String {
    nanoid::format(nanoid::rngs::default, &ALPHANUMERIC, RECORD_ID_LENGTH)
}

/// One canonical Application Telemetry API key: `jtel_` plus a 64-character
/// secret drawn from the operating system's random source.
pub fn generate_api_key() -> String {
    format!(
        "{API_KEY_PREFIX}{}",
        nanoid::format(nanoid::rngs::default, &ALPHANUMERIC, API_KEY_SECRET_LENGTH)
    )
}

/// One developer access token: `jcli_` plus 64 URL-safe characters, which is
/// 384 bits drawn from the operating system's random source.
pub fn generate_access_token() -> String {
    format!(
        "{ACCESS_TOKEN_PREFIX}{}",
        nanoid::format(
            nanoid::rngs::default,
            &nanoid::alphabet::SAFE,
            ACCESS_TOKEN_SECRET_LENGTH
        )
    )
}

/// One CLI sign-in device code: `jdev_` plus 64 URL-safe characters, which is
/// 384 bits drawn from the operating system's random source.
pub fn generate_device_code() -> String {
    format!(
        "{DEVICE_CODE_PREFIX}{}",
        nanoid::format(
            nanoid::rngs::default,
            &nanoid::alphabet::SAFE,
            DEVICE_CODE_SECRET_LENGTH
        )
    )
}

/// Whether text has the shape of a device code.
pub fn is_device_code(text: &str) -> bool {
    text.strip_prefix(DEVICE_CODE_PREFIX).is_some_and(|secret| {
        secret.len() == DEVICE_CODE_SECRET_LENGTH
            && secret
                .chars()
                .all(|character| nanoid::alphabet::SAFE.contains(&character))
    })
}

/// One CLI sign-in user code: eight letters, each drawn uniformly from the
/// user-code alphabet with the operating system's random source. A person is
/// shown the letters in two groups of four.
pub fn generate_user_code() -> String {
    nanoid::format(nanoid::rngs::default, &USER_CODE_ALPHABET, USER_CODE_LENGTH)
}

/// Whether text is the eight letters of a user code.
pub fn is_user_code(text: &str) -> bool {
    text.len() == USER_CODE_LENGTH
        && text
            .chars()
            .all(|character| USER_CODE_ALPHABET.contains(&character))
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use super::*;

    #[test]
    fn identifiers_have_the_documented_shape() {
        let id = generate_id();
        assert_eq!(id.len(), 22);
        assert!(id.chars().all(|c| c.is_ascii_alphanumeric()));
        assert_ne!(id, generate_id());
    }

    #[test]
    fn api_keys_have_the_documented_shape() {
        let key = generate_api_key();
        assert_eq!(key.len(), 69);
        let secret = key.strip_prefix("jtel_").unwrap();
        assert!(secret.chars().all(|c| c.is_ascii_alphanumeric()));
    }

    #[test]
    fn access_tokens_have_the_documented_shape() {
        let token = generate_access_token();
        assert_eq!(token.len(), 69);
        let secret = token.strip_prefix("jcli_").unwrap();
        assert!(
            secret
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
        );
        assert_ne!(token, generate_access_token());
    }

    #[test]
    fn device_codes_have_the_documented_shape() {
        let code = generate_device_code();
        assert_eq!(code.len(), 69);
        let secret = code.strip_prefix("jdev_").unwrap();
        assert!(
            secret
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
        );
        assert_ne!(code, generate_device_code());

        assert!(is_device_code(&code));
        // Another credential, a short secret, a long one, and a character
        // outside the alphabet are not device codes.
        assert!(!is_device_code(&generate_access_token()));
        assert!(!is_device_code(&code[..68]));
        assert!(!is_device_code(&format!("{code}a")));
        assert!(!is_device_code(&format!("jdev_{}", "+".repeat(64))));
        assert!(!is_device_code(""));
    }

    #[test]
    fn user_codes_are_eight_letters_of_the_whole_alphabet() {
        let codes: Vec<String> = (0..500).map(|_| generate_user_code()).collect();
        for code in &codes {
            assert_eq!(code.len(), 8, "{code}");
            assert!(is_user_code(code), "{code}");
        }
        // Every letter is drawn, and nothing else is.
        let drawn: BTreeSet<char> = codes.iter().flat_map(|code| code.chars()).collect();
        assert_eq!(
            drawn.into_iter().collect::<String>(),
            "BCDFGHJKLMNPQRSTVWXZ"
        );

        // Lowercase, a vowel, a hyphen, and another length are not the
        // stored form of a user code.
        for other in [
            "wdjbmjht",
            "WDJBMJHA",
            "WDJB-MJHT",
            "WDJBMJH",
            "WDJBMJHTT",
            "",
        ] {
            assert!(!is_user_code(other), "{other}");
        }
    }
}
