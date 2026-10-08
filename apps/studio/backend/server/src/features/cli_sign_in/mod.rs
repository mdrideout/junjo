//! CLI browser sign-in: the `junjo` CLI obtains a developer access token
//! through a signed-in person's browser. See Studio ADR-012.
//!
//! The flow is the OAuth device authorization grant (RFC 8628) in Studio's
//! own JSON and error conventions:
//!
//! 1. The CLI starts a sign-in. It keeps the device code and shows the person
//!    the short user code.
//! 2. The person, signed in to Studio, confirms the user code and approves or
//!    denies. Approval mints an ordinary developer access token.
//! 3. The CLI polls with the device code and collects the token once.
//!
//! Starting and collecting are public: the terminal has no credential yet,
//! and the device code is the credential for collecting. Reading, approving,
//! and denying need a browser session. A developer access token is not one.
//!
//! Only a pending, unexpired sign-in can be read, approved, or denied.

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::error::{ApiError, ApiJson, ApiPath, ErrorResponse};
use crate::features::auth::{AuthenticatedUser, UserResponse};
use crate::features::evaluation_tokens::{EvaluationTokenScope, TokenName, TokenScopes};
use crate::ids::{
    generate_access_token, generate_device_code, generate_id, generate_user_code, is_device_code,
    is_user_code,
};
use crate::state::AppState;
use crate::timestamps::UtcSeconds;

pub mod repo;

use repo::{Collection, NewSignIn, SignInStatus};

/// How many seconds a CLI sign-in lives: the lifetime `gh auth login` gives
/// its codes, which is long enough for a person to sign in to Studio first.
const SIGN_IN_LIFETIME_SECONDS: i64 = 900;
/// How many seconds the CLI waits between polls: RFC 8628's default.
const POLL_INTERVAL_SECONDS: i64 = 5;
/// The page of the UI where a person approves or denies a sign-in.
const VERIFICATION_PATH: &str = "/cli-sign-in";
/// A person is shown a user code in groups of this many letters.
const USER_CODE_GROUP_LETTERS: usize = 4;

/// A device code as the CLI sends it back: `jdev_` and 64 URL-safe
/// characters.
#[derive(Deserialize)]
#[serde(try_from = "String")]
pub struct DeviceCode(String);

impl TryFrom<String> for DeviceCode {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if !is_device_code(&value) {
            return Err("device_code must be jdev_ followed by 64 URL-safe characters".to_string());
        }
        Ok(Self(value))
    }
}

/// A user code as a person types it or follows it in a link: eight letters in
/// either case, with or without the hyphen between the two groups of four.
/// It is held as it is stored: uppercase, without the hyphen.
#[derive(Deserialize)]
#[serde(try_from = "String")]
pub struct UserCode(String);

impl UserCode {
    /// The code as a person is shown it, such as `WDJB-MJHT`.
    fn shown(&self) -> String {
        let (first, second) = self.0.split_at(USER_CODE_GROUP_LETTERS);
        format!("{first}-{second}")
    }
}

impl TryFrom<String> for UserCode {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        // The hyphen is there for reading, so the code is compared without
        // it and without regard to case.
        let letters = match value.split_once('-') {
            Some((first, second)) if first.len() == USER_CODE_GROUP_LETTERS => {
                format!("{first}{second}")
            }
            _ => value,
        };
        let letters = letters.to_ascii_uppercase();
        if !is_user_code(&letters) {
            return Err(
                "user_code must be eight letters in two groups of four, such as WDJB-MJHT"
                    .to_string(),
            );
        }
        Ok(Self(letters))
    }
}

/// The request to start a CLI sign-in.
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CliSignInStart {
    /// What the terminal calls itself. The approval page shows it, and it
    /// becomes the name of the token.
    #[schema(value_type = String, min_length = 1, max_length = 256, examples("junjo CLI on build-host"))]
    client_name: TokenName,
    /// The scopes the token will hold.
    #[schema(value_type = Vec<EvaluationTokenScope>, min_items = 1, max_items = 3)]
    scopes: TokenScopes,
}

/// A started CLI sign-in.
#[derive(Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CliSignInStarted {
    /// The secret the CLI keeps. It collects the token.
    #[schema(examples("jdev_0123456789_abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKLMNOPQRSTUVWXYZ"))]
    device_code: String,
    /// The code the CLI shows. A person confirms it in the browser.
    #[schema(min_length = 9, max_length = 9, examples("WDJB-MJHT"))]
    user_code: String,
    /// The approval page. The CLI appends it to its configured Studio origin
    /// and adds `?code=<user_code>`.
    #[schema(examples("/cli-sign-in"))]
    verification_path: &'static str,
    /// How many seconds the sign-in lives.
    #[schema(minimum = 1, examples(900))]
    expires_in: i64,
    /// How many seconds the CLI waits between polls.
    #[schema(minimum = 1, examples(5))]
    interval: i64,
}

/// The request to collect the token of a CLI sign-in.
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CliSignInTokenRequest {
    /// The device code the sign-in was started with.
    #[schema(value_type = String, pattern = "^jdev_[A-Za-z0-9_-]{64}$")]
    device_code: DeviceCode,
}

/// How a collected token is presented: always as a bearer credential.
#[derive(Serialize, ToSchema)]
pub enum TokenType {
    #[serde(rename = "bearer")]
    Bearer,
}

/// The developer access token an approved CLI sign-in minted. It is returned
/// once.
#[derive(Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CliSignInToken {
    /// The developer access token value.
    #[schema(examples("jcli_0123456789_abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKLMNOPQRSTUVWXYZ"))]
    pub access_token: String,
    #[schema(inline)]
    pub token_type: TokenType,
    #[schema(min_length = 1, max_length = 64)]
    pub token_id: String,
    #[schema(value_type = Vec<EvaluationTokenScope>)]
    pub scopes: TokenScopes,
    /// When the token stops working. Null: a token minted by a CLI sign-in
    /// works until it is deleted.
    #[schema(value_type = Option<String>, format = DateTime, required)]
    pub expires_at: Option<UtcSeconds>,
}

/// A pending CLI sign-in, as the approval page shows it.
#[derive(Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CliSignInRead {
    /// The code the terminal shows. A person compares the two before
    /// approving.
    #[schema(min_length = 9, max_length = 9, examples("WDJB-MJHT"))]
    user_code: String,
    /// What the terminal calls itself. The terminal chose this text and
    /// Studio has not verified it.
    #[schema(min_length = 1, max_length = 256)]
    client_name: String,
    /// The scopes the token will hold.
    #[schema(value_type = Vec<EvaluationTokenScope>)]
    scopes: TokenScopes,
    /// When the sign-in can no longer be approved.
    #[schema(value_type = String, format = DateTime)]
    expires_at: UtcSeconds,
}

/// The developer access token that approving a CLI sign-in minted.
#[derive(Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CliSignInApproved {
    #[schema(min_length = 1, max_length = 64)]
    pub token_id: String,
    #[schema(min_length = 1, max_length = 256)]
    pub token_name: String,
}

/// This feature's routes, relative to `/api/v1`.
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(start_cli_sign_in))
        .routes(routes!(collect_cli_sign_in_token))
        .routes(routes!(get_cli_sign_in))
        .routes(routes!(approve_cli_sign_in))
        .routes(routes!(deny_cli_sign_in))
}

fn sign_in_not_found() -> ApiError {
    ApiError::not_found("CLI sign-in not found")
}

/// The sign-in is not decided yet. The CLI keeps polling.
fn authorization_pending() -> ApiError {
    ApiError::new(
        StatusCode::BAD_REQUEST,
        "authorization_pending",
        "The CLI sign-in has not been approved or denied yet",
    )
}

/// The person denied the sign-in. The CLI stops.
fn access_denied() -> ApiError {
    ApiError::new(
        StatusCode::BAD_REQUEST,
        "access_denied",
        "The CLI sign-in was denied",
    )
}

/// Nothing can be collected with the device code. The CLI stops, and the
/// person starts again.
fn expired_token() -> ApiError {
    ApiError::new(
        StatusCode::BAD_REQUEST,
        "expired_token",
        "The device code is unknown, already used, or expired",
    )
}

/// Start a CLI sign-in.
///
/// Public: the terminal that asks has no credential yet. Starting also
/// deletes every expired sign-in.
#[utoipa::path(
    post,
    path = "/cli-sign-ins",
    operation_id = "start_cli_sign_in",
    tag = "cli-sign-ins",
    request_body = CliSignInStart,
    responses(
        (status = 201, description = "The started sign-in.", body = CliSignInStarted),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn start_cli_sign_in(
    State(state): State<AppState>,
    ApiJson(request): ApiJson<CliSignInStart>,
) -> Result<(StatusCode, Json<CliSignInStarted>), ApiError> {
    let client_name = request.client_name.into_string();
    loop {
        let device_code = generate_device_code();
        let user_code = UserCode(generate_user_code());
        let created_at = UtcSeconds::now();
        let sign_in = NewSignIn {
            device_code: device_code.clone(),
            user_code: user_code.0.clone(),
            client_name: client_name.clone(),
            scopes: request.scopes,
            created_at,
            expires_at: created_at.plus_seconds(SIGN_IN_LIFETIME_SECONDS),
        };
        let started = state
            .application_db
            .writer
            .call(move |connection| repo::start(connection, &sign_in))
            .await?;
        if started {
            return Ok((
                StatusCode::CREATED,
                Json(CliSignInStarted {
                    device_code,
                    user_code: user_code.shown(),
                    verification_path: VERIFICATION_PATH,
                    expires_in: SIGN_IN_LIFETIME_SECONDS,
                    interval: POLL_INTERVAL_SECONDS,
                }),
            ));
        }
        // Another sign-in has one of the codes. Draw both again.
    }
}

/// Collect the token of a CLI sign-in.
///
/// Public: the device code is the credential. The token is returned once,
/// and the sign-in is deleted with it. Until then the answer is a 400 whose
/// code says why: `authorization_pending` while the sign-in is undecided,
/// `access_denied` once when it was denied, and `expired_token` when the
/// device code is unknown, already used, or expired.
#[utoipa::path(
    post,
    path = "/cli-sign-ins/token",
    operation_id = "collect_cli_sign_in_token",
    tag = "cli-sign-ins",
    request_body = CliSignInTokenRequest,
    responses(
        (status = 200, description = "The token. It is returned once.", body = CliSignInToken),
        (status = 400, description = "Nothing was collected: `authorization_pending`, `access_denied`, or `expired_token`.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn collect_cli_sign_in_token(
    State(state): State<AppState>,
    ApiJson(request): ApiJson<CliSignInTokenRequest>,
) -> Result<Json<CliSignInToken>, ApiError> {
    let device_code = request.device_code.0;

    // A poll that has nothing to collect only reads. The writer is taken once
    // the sign-in is decided, and the transaction there is authoritative.
    let polled = device_code.clone();
    let status = state
        .application_db
        .reader
        .call(move |connection| repo::status(connection, &polled, UtcSeconds::now()))
        .await?;
    match status {
        None => return Err(expired_token()),
        Some(SignInStatus::Pending) => return Err(authorization_pending()),
        Some(SignInStatus::Approved | SignInStatus::Denied) => {}
    }

    let collection = state
        .application_db
        .writer
        .call(move |connection| repo::collect(connection, &device_code, UtcSeconds::now()))
        .await?;
    match collection {
        Collection::Token(token) => Ok(Json(token)),
        Collection::Denied => Err(access_denied()),
        Collection::Pending => Err(authorization_pending()),
        Collection::Expired => Err(expired_token()),
    }
}

/// Get a pending CLI sign-in, for the approval page.
#[utoipa::path(
    get,
    path = "/cli-sign-ins/{user_code}",
    operation_id = "get_cli_sign_in",
    tag = "cli-sign-ins",
    params(("user_code" = String, Path, description = "The user code, in either case, with or without its hyphen.", min_length = 8, max_length = 9)),
    responses(
        (status = 200, description = "The pending sign-in.", body = CliSignInRead),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 404, description = "CLI sign-in not found", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn get_cli_sign_in(
    State(state): State<AppState>,
    _user: AuthenticatedUser,
    ApiPath(user_code): ApiPath<UserCode>,
) -> Result<Json<CliSignInRead>, ApiError> {
    let shown = user_code.shown();
    let sign_in = state
        .application_db
        .reader
        .call(move |connection| repo::pending(connection, &user_code.0, UtcSeconds::now()))
        .await?
        .ok_or_else(sign_in_not_found)?;
    Ok(Json(CliSignInRead {
        user_code: shown,
        client_name: sign_in.client_name,
        scopes: sign_in.scopes,
        expires_at: sign_in.expires_at,
    }))
}

/// Approve a pending CLI sign-in.
///
/// This mints a developer access token with the name and the scopes the
/// terminal asked for and no expiry. It belongs to the approving user, and
/// the terminal collects it.
#[utoipa::path(
    post,
    path = "/cli-sign-ins/{user_code}/approve",
    operation_id = "approve_cli_sign_in",
    tag = "cli-sign-ins",
    params(("user_code" = String, Path, description = "The user code, in either case, with or without its hyphen.", min_length = 8, max_length = 9)),
    responses(
        (status = 200, description = "The minted token.", body = CliSignInApproved),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 404, description = "CLI sign-in not found", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn approve_cli_sign_in(
    State(state): State<AppState>,
    user: AuthenticatedUser,
    ApiPath(user_code): ApiPath<UserCode>,
) -> Result<Json<CliSignInApproved>, ApiError> {
    let token_id = generate_id();
    let token = generate_access_token();
    let user_id = user.user_id.clone();
    let approved = state
        .application_db
        .writer
        .call(move |connection| {
            repo::approve(
                connection,
                &user_code.0,
                &token_id,
                &token,
                &user_id,
                UtcSeconds::now(),
            )
        })
        .await?
        .ok_or_else(sign_in_not_found)?;
    tracing::info!(
        audit = true,
        action = "approve",
        resource_type = "cli_sign_in",
        token_id = %approved.token_id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        "AUDIT: APPROVE cli_sign_in"
    );
    Ok(Json(approved))
}

/// Deny a pending CLI sign-in. The terminal is told once and gets no token.
#[utoipa::path(
    post,
    path = "/cli-sign-ins/{user_code}/deny",
    operation_id = "deny_cli_sign_in",
    tag = "cli-sign-ins",
    params(("user_code" = String, Path, description = "The user code, in either case, with or without its hyphen.", min_length = 8, max_length = 9)),
    responses(
        (status = 200, description = "The sign-in was denied.", body = UserResponse),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 404, description = "CLI sign-in not found", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn deny_cli_sign_in(
    State(state): State<AppState>,
    user: AuthenticatedUser,
    ApiPath(user_code): ApiPath<UserCode>,
) -> Result<Json<UserResponse>, ApiError> {
    let denied = state
        .application_db
        .writer
        .call(move |connection| repo::deny(connection, &user_code.0, UtcSeconds::now()))
        .await?;
    if !denied {
        return Err(sign_in_not_found());
    }
    tracing::info!(
        audit = true,
        action = "deny",
        resource_type = "cli_sign_in",
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        "AUDIT: DENY cli_sign_in"
    );
    Ok(Json(UserResponse {
        message: "CLI sign-in denied",
    }))
}

#[cfg(test)]
mod tests;
