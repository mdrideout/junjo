//! Password hashing with bcrypt.
//!
//! bcrypt reads at most 72 bytes of input. A longer password is refused when
//! it is set and never verifies, so a password is never silently truncated.

use crate::error::ApiError;

/// The longest password bcrypt reads in full.
pub const MAX_PASSWORD_BYTES: usize = 72;

/// bcrypt work factor. Kept at 12, the value existing deployments use.
const BCRYPT_COST: u32 = 12;

/// Hash a password off the async executor: bcrypt is deliberately slow.
///
/// The password is at most `MAX_PASSWORD_BYTES` long: request validation
/// refuses a longer one. The crate's "non-truncating" functions are not used
/// because they also refuse exactly 72 bytes, which bcrypt reads in full.
pub async fn hash_password(password: String) -> Result<String, ApiError> {
    tokio::task::spawn_blocking(move || bcrypt::hash(password, BCRYPT_COST))
        .await
        .map_err(|error| {
            tracing::error!(%error, "password hashing task failed");
            ApiError::internal()
        })?
        .map_err(|error| {
            tracing::error!(%error, "password hashing failed");
            ApiError::internal()
        })
}

/// Verify a password against a stored hash. Any failure is "not verified".
pub async fn verify_password(password: String, hash: String) -> bool {
    // No stored password is this long, and bcrypt would compare only the
    // first 72 bytes.
    if password.len() > MAX_PASSWORD_BYTES {
        return false;
    }
    tokio::task::spawn_blocking(move || bcrypt::verify(password, &hash).unwrap_or(false))
        .await
        .unwrap_or(false)
}
