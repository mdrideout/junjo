//! Developer access tokens: the scoped bearer credential for the CLI, the
//! SDK, and automation. The API calls them evaluation tokens.
//!
//! Only a signed-in user manages tokens. The one thing a token may do to
//! tokens is describe and revoke itself.

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use serde::{Deserialize, Serialize};
use utoipa::{IntoParams, ToSchema};
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::error::{ApiError, ApiJson, ApiPath, ApiQuery, ErrorResponse};
use crate::features::auth::AuthenticatedUser;
use crate::ids::{generate_access_token, generate_id};
use crate::pagination::{Cursor, PageLimit, TimePosition, decode_time_cursor, encode_time_cursor};
use crate::state::AppState;
use crate::text;
use crate::timestamps::{RequestTimestamp, UtcSeconds};

pub mod access;
pub mod repo;

use access::CurrentToken;

const MAX_TOKEN_NAME_BYTES: usize = 256;
const MAX_TOKEN_ID_CHARACTERS: usize = 64;
/// Names this listing in its cursors.
const CURSOR_KIND: &str = "evaluation-tokens";

/// Authorities supported by the evaluation control/query credential.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub enum EvaluationTokenScope {
    #[serde(rename = "evaluation:read")]
    EvaluationRead,
    #[serde(rename = "evaluation:write")]
    EvaluationWrite,
    #[serde(rename = "evidence:read")]
    EvidenceRead,
}

/// Every scope, in the order the API lists them.
const SCOPE_ORDER: [EvaluationTokenScope; 3] = [
    EvaluationTokenScope::EvaluationRead,
    EvaluationTokenScope::EvaluationWrite,
    EvaluationTokenScope::EvidenceRead,
];

/// The scopes one token holds: at least one, each at most once.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(
    try_from = "Vec<EvaluationTokenScope>",
    into = "Vec<EvaluationTokenScope>"
)]
pub struct TokenScopes {
    pub evaluation_read: bool,
    pub evaluation_write: bool,
    pub evidence_read: bool,
}

impl TokenScopes {
    pub fn contains(self, scope: EvaluationTokenScope) -> bool {
        match scope {
            EvaluationTokenScope::EvaluationRead => self.evaluation_read,
            EvaluationTokenScope::EvaluationWrite => self.evaluation_write,
            EvaluationTokenScope::EvidenceRead => self.evidence_read,
        }
    }
}

impl TryFrom<Vec<EvaluationTokenScope>> for TokenScopes {
    type Error = String;

    fn try_from(scopes: Vec<EvaluationTokenScope>) -> Result<Self, Self::Error> {
        if scopes.is_empty() {
            return Err("scopes must contain at least one scope".to_string());
        }
        let mut held = Self {
            evaluation_read: false,
            evaluation_write: false,
            evidence_read: false,
        };
        for scope in scopes {
            let slot = match scope {
                EvaluationTokenScope::EvaluationRead => &mut held.evaluation_read,
                EvaluationTokenScope::EvaluationWrite => &mut held.evaluation_write,
                EvaluationTokenScope::EvidenceRead => &mut held.evidence_read,
            };
            if *slot {
                return Err("scopes must not contain duplicates".to_string());
            }
            *slot = true;
        }
        Ok(held)
    }
}

impl From<TokenScopes> for Vec<EvaluationTokenScope> {
    fn from(scopes: TokenScopes) -> Self {
        SCOPE_ORDER
            .into_iter()
            .filter(|scope| scopes.contains(*scope))
            .collect()
    }
}

/// A token name: 1 to 256 bytes with no surrounding whitespace.
#[derive(Debug, Deserialize)]
#[serde(try_from = "String")]
pub struct TokenName(String);

impl TokenName {
    pub fn into_string(self) -> String {
        self.0
    }
}

impl TryFrom<String> for TokenName {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        let trimmed = text::trimmed(&value);
        if trimmed.is_empty() {
            return Err("name must not be blank".to_string());
        }
        if trimmed.len() != value.len() {
            return Err("name must not contain surrounding whitespace".to_string());
        }
        if value.len() > MAX_TOKEN_NAME_BYTES {
            return Err(format!(
                "name must be at most {MAX_TOKEN_NAME_BYTES} UTF-8 bytes"
            ));
        }
        Ok(Self(value))
    }
}

/// A token identifier as a caller sends it: 1 to 64 characters.
#[derive(Debug, Deserialize)]
#[serde(try_from = "String")]
pub struct TokenId(String);

impl TryFrom<String> for TokenId {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if value.is_empty() || value.chars().count() > MAX_TOKEN_ID_CHARACTERS {
            return Err(format!(
                "token_id must be 1 to {MAX_TOKEN_ID_CHARACTERS} characters"
            ));
        }
        Ok(Self(value))
    }
}

/// The request to create a developer access token.
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationTokenCreate {
    #[schema(value_type = String, min_length = 1, max_length = 256)]
    name: TokenName,
    #[schema(value_type = Vec<EvaluationTokenScope>, min_items = 1, max_items = 3)]
    scopes: TokenScopes,
    /// When the token stops working. A token without an expiry works until
    /// it is deleted.
    #[schema(value_type = Option<String>, format = DateTime)]
    expires_at: Option<RequestTimestamp>,
}

/// One developer access token. The token value is recoverable by design
/// (Studio ADR-010).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationTokenRead {
    #[schema(min_length = 1, max_length = 64)]
    pub id: String,
    #[schema(min_length = 1, max_length = 256)]
    pub name: String,
    /// Recoverable bearer token managed by authenticated Studio users.
    #[schema(examples("jcli_0123456789_abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKLMNOPQRSTUVWXYZ"))]
    pub token: String,
    #[schema(value_type = Vec<EvaluationTokenScope>)]
    pub scopes: TokenScopes,
    #[schema(value_type = Option<String>, format = DateTime, required)]
    pub expires_at: Option<UtcSeconds>,
    /// The user who created the token. Null once that user is deleted.
    #[schema(required, min_length = 1, max_length = 64)]
    pub created_by_user_id: Option<String>,
    #[schema(value_type = String, format = DateTime)]
    pub created_at: UtcSeconds,
}

/// One page of developer access tokens, newest first.
#[derive(Debug, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationTokenList {
    #[schema(max_items = 100)]
    pub items: Vec<EvaluationTokenRead>,
    /// Send this as `cursor` to read the next page. Null on the last page.
    #[schema(required)]
    pub next_cursor: Option<String>,
}

/// What a developer access token is told about itself. The token value is
/// not repeated.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationTokenCurrent {
    #[schema(min_length = 1, max_length = 64)]
    pub id: String,
    #[schema(min_length = 1, max_length = 256)]
    pub name: String,
    #[schema(value_type = Vec<EvaluationTokenScope>)]
    pub scopes: TokenScopes,
    #[schema(value_type = Option<String>, format = DateTime, required)]
    pub expires_at: Option<UtcSeconds>,
    #[schema(value_type = String, format = DateTime)]
    pub created_at: UtcSeconds,
}

/// This feature's routes, relative to `/api/v1`.
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(create_evaluation_token, list_evaluation_tokens))
        .routes(routes!(
            get_current_evaluation_token,
            delete_current_evaluation_token
        ))
        .routes(routes!(delete_evaluation_token))
}

/// Create a developer access token.
#[utoipa::path(
    post,
    path = "/evaluation-tokens",
    operation_id = "create_evaluation_token",
    tag = "evaluation-tokens",
    request_body = EvaluationTokenCreate,
    responses(
        (status = 201, description = "The created token.", body = EvaluationTokenRead),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn create_evaluation_token(
    State(state): State<AppState>,
    user: AuthenticatedUser,
    ApiJson(request): ApiJson<EvaluationTokenCreate>,
) -> Result<(StatusCode, Json<EvaluationTokenRead>), ApiError> {
    if request
        .expires_at
        .is_some_and(|expiry| !expiry.is_in_the_future())
    {
        return Err(ApiError::validation("expires_at must be in the future"));
    }
    let token = EvaluationTokenRead {
        id: generate_id(),
        name: request.name.0,
        token: generate_access_token(),
        scopes: request.scopes,
        expires_at: request.expires_at.map(RequestTimestamp::to_seconds),
        created_by_user_id: Some(user.user_id.clone()),
        created_at: UtcSeconds::now(),
    };
    let stored = token.clone();
    state
        .application_db
        .writer
        .call(move |connection| repo::create(connection, &stored))
        .await?;
    tracing::info!(
        audit = true,
        action = "create",
        resource_type = "evaluation_token",
        resource_id = %token.id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        name = %token.name,
        evaluation_read = token.scopes.evaluation_read,
        evaluation_write = token.scopes.evaluation_write,
        evidence_read = token.scopes.evidence_read,
        "AUDIT: CREATE evaluation_token"
    );
    Ok((StatusCode::CREATED, Json(token)))
}

/// The page of a token listing to read.
#[derive(Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct ListTokensQuery {
    /// The `next_cursor` of the previous page.
    #[param(value_type = Option<String>, min_length = 1, max_length = 1024)]
    cursor: Option<Cursor>,
    /// The most tokens to return.
    #[param(value_type = u32, minimum = 1, maximum = 100, default = 50)]
    #[serde(default)]
    limit: PageLimit,
}

/// List developer access tokens, newest first.
#[utoipa::path(
    get,
    path = "/evaluation-tokens",
    operation_id = "list_evaluation_tokens",
    tag = "evaluation-tokens",
    params(ListTokensQuery),
    responses(
        (status = 200, description = "One page of tokens.", body = EvaluationTokenList),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn list_evaluation_tokens(
    State(state): State<AppState>,
    _user: AuthenticatedUser,
    ApiQuery(query): ApiQuery<ListTokensQuery>,
) -> Result<Json<EvaluationTokenList>, ApiError> {
    let after = query
        .cursor
        .as_ref()
        .map(|cursor| decode_time_cursor(CURSOR_KIND, cursor))
        .transpose()?;
    let limit = query.limit.get();
    // One row past the page says whether another page follows.
    let mut items = state
        .application_db
        .reader
        .call(move |connection| repo::list(connection, after.as_ref(), limit + 1))
        .await?;
    let has_more = items.len() > limit as usize;
    items.truncate(limit as usize);
    let next_cursor = items.last().filter(|_| has_more).map(|last| {
        encode_time_cursor(
            CURSOR_KIND,
            &TimePosition {
                created_at: last.created_at,
                id: last.id.clone(),
            },
        )
    });
    Ok(Json(EvaluationTokenList { items, next_cursor }))
}

/// Delete one developer access token. It stops working on the next request.
#[utoipa::path(
    delete,
    path = "/evaluation-tokens/{token_id}",
    operation_id = "delete_evaluation_token",
    tag = "evaluation-tokens",
    params(("token_id" = String, Path, description = "The token's identifier.", min_length = 1, max_length = 64)),
    responses(
        (status = 204, description = "The token was deleted."),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 404, description = "Access token not found", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn delete_evaluation_token(
    State(state): State<AppState>,
    user: AuthenticatedUser,
    ApiPath(token_id): ApiPath<TokenId>,
) -> Result<StatusCode, ApiError> {
    let id = token_id.0;
    let deleted_id = id.clone();
    let deleted = state
        .application_db
        .writer
        .call(move |connection| repo::delete(connection, &deleted_id))
        .await?;
    if !deleted {
        return Err(ApiError::not_found("Access token not found"));
    }
    tracing::info!(
        audit = true,
        action = "delete",
        resource_type = "evaluation_token",
        resource_id = %id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        "AUDIT: DELETE evaluation_token"
    );
    Ok(StatusCode::NO_CONTENT)
}

/// Describe the developer access token that makes the request.
///
/// Any valid token may ask, whatever its scopes. A browser session is not a
/// credential for this route.
#[utoipa::path(
    get,
    path = "/evaluation-tokens/current",
    operation_id = "get_current_evaluation_token",
    tag = "evaluation-tokens",
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The token that made the request.", body = EvaluationTokenCurrent),
        (status = 401, description = "No valid token.", body = ErrorResponse),
    )
)]
pub async fn get_current_evaluation_token(
    State(state): State<AppState>,
    token: CurrentToken,
) -> Result<Json<EvaluationTokenCurrent>, ApiError> {
    let current = state
        .application_db
        .reader
        .call(move |connection| repo::current(connection, &token.id))
        .await?
        // The token was deleted after it authenticated this request.
        .ok_or_else(access::invalid_token)?;
    Ok(Json(current))
}

/// Delete the developer access token that makes the request.
///
/// It stops working on the next request. Any valid token may revoke itself,
/// whatever its scopes. A browser session is not a credential for this route.
#[utoipa::path(
    delete,
    path = "/evaluation-tokens/current",
    operation_id = "delete_current_evaluation_token",
    tag = "evaluation-tokens",
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 204, description = "The token was deleted."),
        (status = 401, description = "No valid token.", body = ErrorResponse),
    )
)]
pub async fn delete_current_evaluation_token(
    State(state): State<AppState>,
    token: CurrentToken,
) -> Result<StatusCode, ApiError> {
    let deleted_id = token.id.clone();
    let deleted = state
        .application_db
        .writer
        .call(move |connection| repo::delete(connection, &deleted_id))
        .await?;
    if !deleted {
        // The token was deleted after it authenticated this request.
        return Err(access::invalid_token());
    }
    tracing::info!(
        audit = true,
        action = "delete",
        resource_type = "evaluation_token",
        resource_id = %token.id,
        user_id = %token.user.user_id,
        user_email = %token.user.email,
        session_audit_id = %token.user.audit_id,
        "AUDIT: DELETE evaluation_token"
    );
    Ok(StatusCode::NO_CONTENT)
}

#[cfg(test)]
mod tests;
