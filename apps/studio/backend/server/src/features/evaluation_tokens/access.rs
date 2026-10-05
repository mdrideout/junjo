//! Who may call a token-protected route: a developer access token that holds
//! the route's scope, or a signed-in user.
//!
//! A bearer credential takes precedence over a session. A request that sends
//! an `Authorization` header is judged by that header alone.
//!
//! The routes on which a token acts on itself take a token only. A session is
//! not a credential for them.

use axum::extract::FromRequestParts;
use axum::http::header::AUTHORIZATION;
use axum::http::request::Parts;
use axum::http::{HeaderValue, StatusCode};
use serde_json::json;

use super::repo::TokenCredential;
use super::{EvaluationTokenScope, repo};
use crate::error::ApiError;
use crate::features::auth::AuthenticatedUser;
use crate::state::AppState;
use crate::timestamps::UtcSeconds;

/// The caller may read evaluation datasets, runs, and attempts.
pub struct EvaluationReadAccess;

/// The caller may create and change evaluation datasets, runs, and attempts.
/// It carries who the caller is, for the audit event of each change.
pub struct EvaluationWriteAccess(pub AuthenticatedUser);

/// The caller may read execution evidence.
pub struct EvidenceReadAccess;

/// The caller is a developer access token acting on itself. Any valid token
/// passes, whatever its scopes. A session does not.
pub struct CurrentToken {
    /// The token's identifier.
    pub id: String,
    /// Who the caller is, for the audit event of a change.
    pub user: AuthenticatedUser,
}

impl FromRequestParts<AppState> for EvaluationReadAccess {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &AppState) -> Result<Self, ApiError> {
        authorize(parts, state, EvaluationTokenScope::EvaluationRead)
            .await
            .map(|_| Self)
    }
}

impl FromRequestParts<AppState> for EvaluationWriteAccess {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &AppState) -> Result<Self, ApiError> {
        authorize(parts, state, EvaluationTokenScope::EvaluationWrite)
            .await
            .map(Self)
    }
}

impl FromRequestParts<AppState> for EvidenceReadAccess {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &AppState) -> Result<Self, ApiError> {
        authorize(parts, state, EvaluationTokenScope::EvidenceRead)
            .await
            .map(|_| Self)
    }
}

impl FromRequestParts<AppState> for CurrentToken {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &AppState) -> Result<Self, ApiError> {
        let Some(header) = parts.headers.get(AUTHORIZATION) else {
            return Err(unauthorized(
                "Missing evaluation token authorization header",
            ));
        };
        let credential = valid_token(header, state).await?;
        Ok(Self {
            id: credential.id.clone(),
            user: token_user(credential),
        })
    }
}

fn unauthorized(message: &str) -> ApiError {
    ApiError::unauthorized(message).with_bearer_challenge()
}

/// The refusal of a token that is unknown or expired, or whose creator is
/// inactive or deleted.
pub fn invalid_token() -> ApiError {
    unauthorized("Invalid or expired evaluation token")
}

/// The credentials of an `Authorization: Bearer <credentials>` header.
fn bearer_credentials(header: &HeaderValue) -> Option<&str> {
    let (scheme, credentials) = header.to_str().ok()?.split_once(' ')?;
    let credentials = credentials.trim();
    (scheme.eq_ignore_ascii_case("bearer") && !credentials.is_empty()).then_some(credentials)
}

/// The token an `Authorization` header names, once it is known to work: it
/// exists, it has not expired, and its creator is an active user.
async fn valid_token(header: &HeaderValue, state: &AppState) -> Result<TokenCredential, ApiError> {
    let Some(token) = bearer_credentials(header) else {
        return Err(unauthorized(
            "Invalid evaluation token authorization header",
        ));
    };

    let token = token.to_string();
    let credential = state
        .application_db
        .reader
        .call(move |connection| repo::credential(connection, &token))
        .await?;
    let now = UtcSeconds::now();
    credential
        .filter(|credential| {
            credential.user_is_active && credential.expires_at.is_none_or(|expiry| expiry > now)
        })
        .ok_or_else(invalid_token)
}

/// A token's caller: the user who created the token, attributed to the token.
fn token_user(credential: TokenCredential) -> AuthenticatedUser {
    AuthenticatedUser {
        user_id: credential.user_id,
        email: credential.user_email,
        audit_id: format!("evaluation-token:{}", credential.id),
    }
}

async fn authorize(
    parts: &mut Parts,
    state: &AppState,
    required: EvaluationTokenScope,
) -> Result<AuthenticatedUser, ApiError> {
    let Some(header) = parts.headers.get(AUTHORIZATION) else {
        return AuthenticatedUser::from_request_parts(parts, state).await;
    };
    let credential = valid_token(header, state).await?;
    if !credential.scopes.contains(required) {
        return Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "insufficient_evaluation_token_scope",
            "Evaluation token lacks the required scope.",
        )
        .with_extra("missing_scopes", json!([required])));
    }
    Ok(token_user(credential))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn credentials(header: &'static str) -> Option<&'static str> {
        // The header value must outlive the borrow, so leak the test value.
        let header: &'static HeaderValue = Box::leak(Box::new(HeaderValue::from_static(header)));
        bearer_credentials(header)
    }

    #[test]
    fn only_a_bearer_header_with_credentials_is_read() {
        assert_eq!(credentials("Bearer jcli_abc"), Some("jcli_abc"));
        assert_eq!(credentials("bearer jcli_abc"), Some("jcli_abc"));
        assert_eq!(credentials("Bearer   jcli_abc  "), Some("jcli_abc"));
        assert_eq!(credentials("Basic abc"), None);
        assert_eq!(credentials("Bearer"), None);
        assert_eq!(credentials("Bearer "), None);
        assert_eq!(credentials("jcli_abc"), None);
    }
}
