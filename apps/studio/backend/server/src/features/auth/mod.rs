//! Browser authentication: first-user setup, sessions, and the authenticated
//! user extractor. See Studio ADR-012.

use axum::Json;
use axum::extract::{FromRequestParts, State};
use axum::http::StatusCode;
use axum::http::request::Parts;
use serde::{Deserialize, Serialize};
use time::Duration;
use tower_sessions::cookie::SameSite;
use tower_sessions::{Expiry, Session, SessionManagerLayer};
use utoipa::ToSchema;
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::error::{ApiError, ApiJson, ApiPath, ErrorResponse};
use crate::ids::generate_id;
use crate::state::AppState;
use crate::timestamps::UtcSeconds;

pub mod password;
pub mod session_store;
pub mod users;

use session_store::SqliteSessionStore;
use users::{FirstUserOutcome, User};

const SESSION_COOKIE_NAME: &str = "junjo_session";
const SESSION_LIFETIME: Duration = Duration::days(30);
/// Activity renews a session, but the renewal is written at most this often.
/// `tower-sessions` extends expiry only when a session is saved, and saving
/// on every request would turn every authenticated read into a write.
const SESSION_RENEWAL_INTERVAL_SECONDS: i64 = 24 * 60 * 60;

const SESSION_USER_ID: &str = "user_id";
const SESSION_AUDIT_ID: &str = "audit_id";
const SESSION_AUTHENTICATED_AT: &str = "authenticated_at";
const SESSION_RENEWED_AT: &str = "renewed_at";

const MIN_PASSWORD_CHARACTERS: usize = 8;

/// The session layer: an opaque, host-only cookie and a 30-day lifetime.
pub fn session_layer(
    store: SqliteSessionStore,
    is_production: bool,
) -> SessionManagerLayer<SqliteSessionStore> {
    SessionManagerLayer::new(store)
        .with_name(SESSION_COOKIE_NAME)
        .with_http_only(true)
        .with_same_site(SameSite::Strict)
        .with_secure(is_production)
        .with_expiry(Expiry::OnInactivity(SESSION_LIFETIME))
}

/// An email address, validated and lowercased.
#[derive(Debug, Clone, Deserialize)]
#[serde(try_from = "String")]
pub struct Email(String);

impl TryFrom<String> for Email {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        let trimmed = value.trim();
        // A plain address whose domain has a dot. The crate's defaults also
        // accept `Name <address>`, `user@[127.0.0.1]`, and `user@localhost`.
        let options = email_address::Options::default()
            .with_required_tld()
            .without_domain_literal()
            .without_display_text();
        if email_address::EmailAddress::parse_with_options(trimmed, options).is_err() {
            return Err("value is not a valid email address".to_string());
        }
        Ok(Self(trimmed.to_lowercase()))
    }
}

/// A password that bcrypt can hash without truncation.
#[derive(Deserialize)]
#[serde(try_from = "String")]
pub struct Password(String);

impl TryFrom<String> for Password {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if value.chars().count() < MIN_PASSWORD_CHARACTERS {
            return Err(format!(
                "Password must be at least {MIN_PASSWORD_CHARACTERS} characters"
            ));
        }
        if value.len() > password::MAX_PASSWORD_BYTES {
            return Err(format!(
                "Password must be at most {} bytes",
                password::MAX_PASSWORD_BYTES
            ));
        }
        Ok(Self(value))
    }
}

/// The signed-in user, with the context audit events record.
#[derive(Debug, Clone)]
pub struct AuthenticatedUser {
    pub user_id: String,
    pub email: String,
    /// A per-session identifier for audit correlation. It is not the session
    /// credential.
    pub audit_id: String,
}

fn session_error(error: tower_sessions::session::Error) -> ApiError {
    tracing::error!(%error, "session store operation failed");
    ApiError::internal()
}

impl FromRequestParts<AppState> for AuthenticatedUser {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &AppState) -> Result<Self, ApiError> {
        let session = Session::from_request_parts(parts, state)
            .await
            .map_err(|(_, message)| {
                tracing::error!(message, "session layer is missing");
                ApiError::internal()
            })?;
        let user_id: Option<String> = session.get(SESSION_USER_ID).await.map_err(session_error)?;
        let Some(user_id) = user_id else {
            return Err(ApiError::unauthorized("No valid session"));
        };
        let user = state
            .application_db
            .reader
            .call(move |connection| users::user_by_id(connection, &user_id))
            .await?;
        // A deleted or inactive user's sessions stop working here.
        let Some(user) = user.filter(|user| user.is_active) else {
            return Err(ApiError::unauthorized("User not found"));
        };

        let now = UtcSeconds::now().as_unix();
        let renewed_at: Option<i64> = session
            .get(SESSION_RENEWED_AT)
            .await
            .map_err(session_error)?;
        if renewed_at.is_none_or(|renewed_at| now - renewed_at >= SESSION_RENEWAL_INTERVAL_SECONDS)
        {
            session
                .insert(SESSION_RENEWED_AT, now)
                .await
                .map_err(session_error)?;
        }

        let audit_id: Option<String> =
            session.get(SESSION_AUDIT_ID).await.map_err(session_error)?;
        Ok(Self {
            user_id: user.id,
            email: user.email,
            audit_id: audit_id.unwrap_or_default(),
        })
    }
}

/// Bind a user to the session. The identifier is rotated first, so a session
/// identifier issued before sign-in is never promoted to an authenticated one.
async fn bind_session(session: &Session, user_id: &str) -> Result<(), ApiError> {
    session.cycle_id().await.map_err(session_error)?;
    let now = UtcSeconds::now();
    session
        .insert(SESSION_USER_ID, user_id)
        .await
        .map_err(session_error)?;
    session
        .insert(SESSION_AUDIT_ID, generate_id())
        .await
        .map_err(session_error)?;
    session
        .insert(SESSION_AUTHENTICATED_AT, now.format())
        .await
        .map_err(session_error)?;
    session
        .insert(SESSION_RENEWED_AT, now.as_unix())
        .await
        .map_err(session_error)?;
    Ok(())
}

/// This feature's routes, relative to `/api/v1`.
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(db_has_users))
        .routes(routes!(create_first_user))
        .routes(routes!(sign_in))
        .routes(routes!(sign_out))
        .routes(routes!(auth_test))
        .routes(routes!(list_users, create_user))
        .routes(routes!(delete_user))
}

/// Whether any user exists.
#[derive(Serialize, ToSchema)]
pub struct DbHasUsersResponse {
    users_exist: bool,
}

/// Report whether any user exists.
///
/// Public: a fresh deployment uses it to decide between first-user setup and
/// sign-in.
#[utoipa::path(
    get,
    path = "/users/db-has-users",
    operation_id = "db_has_users",
    tag = "auth",
    responses((status = 200, description = "Whether any user exists.", body = DbHasUsersResponse))
)]
pub async fn db_has_users(
    State(state): State<AppState>,
) -> Result<Json<DbHasUsersResponse>, ApiError> {
    let users_exist = state
        .application_db
        .reader
        .call(|connection| users::has_users(connection))
        .await?;
    Ok(Json(DbHasUsersResponse { users_exist }))
}

/// The request to create a user.
#[derive(Deserialize, ToSchema)]
pub struct CreateUserRequest {
    #[schema(value_type = String, format = Email)]
    email: Email,
    #[schema(value_type = String, min_length = 8)]
    password: Password,
}

/// The response after a successful user operation.
#[derive(Serialize, ToSchema)]
pub struct UserResponse {
    pub message: &'static str,
}

fn users_already_exist() -> ApiError {
    ApiError::new(
        StatusCode::BAD_REQUEST,
        "users_already_exist",
        "Users already exist, cannot create first user",
    )
}

/// Create the first user and sign them in.
///
/// Public so a fresh deployment can bootstrap. It is refused once any user
/// exists.
#[utoipa::path(
    post,
    path = "/users/create-first-user",
    operation_id = "create_first_user",
    tag = "auth",
    request_body = CreateUserRequest,
    responses(
        (status = 200, description = "The first user was created and signed in.", body = UserResponse),
        (status = 400, description = "A user already exists.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn create_first_user(
    State(state): State<AppState>,
    session: Session,
    ApiJson(request): ApiJson<CreateUserRequest>,
) -> Result<Json<UserResponse>, ApiError> {
    // Reject the steady-state path before spending bcrypt CPU or taking the
    // writer. The transaction below repeats the check and is authoritative.
    let users_exist = state
        .application_db
        .reader
        .call(|connection| users::has_users(connection))
        .await?;
    if users_exist {
        return Err(users_already_exist());
    }

    let password_hash = password::hash_password(request.password.0).await?;
    let id = generate_id();
    let email = request.email.0;
    let outcome = state
        .application_db
        .writer
        .call(move |connection| {
            users::create_first_user(connection, &id, &email, &password_hash, UtcSeconds::now())
        })
        .await?;
    let FirstUserOutcome::Created(user) = outcome else {
        return Err(users_already_exist());
    };

    start_session(&state, &session, &user.id).await?;
    tracing::info!(
        audit = true,
        action = "create",
        resource_type = "user",
        resource_id = %user.id,
        created_email = %user.email,
        first_user = true,
        "AUDIT: CREATE user"
    );
    Ok(Json(UserResponse {
        message: "First user created successfully",
    }))
}

/// Start an authenticated session. Expired sessions are removed first, so the
/// table grows only with sessions that can still be used.
async fn start_session(state: &AppState, session: &Session, user_id: &str) -> Result<(), ApiError> {
    if let Err(error) = state.session_store.delete_expired().await {
        tracing::warn!(%error, "expired session cleanup failed");
    }
    bind_session(session, user_id).await
}

/// The request to sign in.
#[derive(Deserialize, ToSchema)]
pub struct SignInRequest {
    #[schema(value_type = String, format = Email)]
    email: Email,
    password: String,
}

fn invalid_credentials() -> ApiError {
    ApiError::unauthorized("Invalid credentials")
}

/// Sign in with an email address and a password.
#[utoipa::path(
    post,
    path = "/sign-in",
    operation_id = "sign_in",
    tag = "auth",
    request_body = SignInRequest,
    responses(
        (status = 200, description = "The user is signed in.", body = UserResponse),
        (status = 401, description = "The credentials are not valid.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn sign_in(
    State(state): State<AppState>,
    session: Session,
    ApiJson(request): ApiJson<SignInRequest>,
) -> Result<Json<UserResponse>, ApiError> {
    let email = request.email.0;
    let lookup = email.clone();
    let credentials = state
        .application_db
        .reader
        .call(move |connection| users::credentials_by_email(connection, &lookup))
        .await?;
    // An unknown address, an inactive user, and a wrong password are one
    // answer.
    let verified = match credentials.filter(|credentials| credentials.is_active) {
        Some(credentials) => password::verify_password(request.password, credentials.password_hash)
            .await
            .then_some(credentials.id),
        None => None,
    };
    let Some(user_id) = verified else {
        tracing::warn!(%email, "sign-in refused");
        return Err(invalid_credentials());
    };

    start_session(&state, &session, &user_id).await?;
    tracing::info!(
        audit = true,
        action = "auth_login",
        resource_type = "session",
        user_id = %user_id,
        user_email = %email,
        "AUDIT: AUTH_LOGIN session"
    );
    Ok(Json(UserResponse {
        message: "signed in",
    }))
}

/// Sign out. This ends the session that made the request and no other.
#[utoipa::path(
    post,
    path = "/sign-out",
    operation_id = "sign_out",
    tag = "auth",
    responses(
        (status = 200, description = "The session is ended.", body = UserResponse),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
    )
)]
pub async fn sign_out(
    user: AuthenticatedUser,
    session: Session,
) -> Result<Json<UserResponse>, ApiError> {
    session.flush().await.map_err(session_error)?;
    tracing::info!(
        audit = true,
        action = "auth_logout",
        resource_type = "session",
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        "AUDIT: AUTH_LOGOUT session"
    );
    Ok(Json(UserResponse {
        message: "signed out",
    }))
}

/// The signed-in user.
#[derive(Serialize, ToSchema)]
pub struct AuthTestResponse {
    #[schema(format = Email)]
    user_email: String,
}

/// Return the signed-in user's email.
#[utoipa::path(
    get,
    path = "/auth-test",
    operation_id = "auth_test",
    tag = "auth",
    responses(
        (status = 200, description = "The signed-in user.", body = AuthTestResponse),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
    )
)]
pub async fn auth_test(user: AuthenticatedUser) -> Json<AuthTestResponse> {
    Json(AuthTestResponse {
        user_email: user.email,
    })
}

/// List every user, oldest first.
#[utoipa::path(
    get,
    path = "/users",
    operation_id = "list_users",
    tag = "auth",
    responses(
        (status = 200, description = "Every user.", body = Vec<User>),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
    )
)]
pub async fn list_users(
    State(state): State<AppState>,
    _user: AuthenticatedUser,
) -> Result<Json<Vec<User>>, ApiError> {
    let users = state
        .application_db
        .reader
        .call(|connection| users::list(connection))
        .await?;
    Ok(Json(users))
}

/// Create a user. Users are equal: any signed-in user may create, list, and
/// delete users.
#[utoipa::path(
    post,
    path = "/users",
    operation_id = "create_user",
    tag = "auth",
    request_body = CreateUserRequest,
    responses(
        (status = 200, description = "The user was created.", body = UserResponse),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 409, description = "The email address is already in use.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn create_user(
    State(state): State<AppState>,
    user: AuthenticatedUser,
    ApiJson(request): ApiJson<CreateUserRequest>,
) -> Result<Json<UserResponse>, ApiError> {
    let password_hash = password::hash_password(request.password.0).await?;
    let id = generate_id();
    let email = request.email.0;
    let created = state
        .application_db
        .writer
        .call(move |connection| {
            users::create_user(connection, &id, &email, &password_hash, UtcSeconds::now())
        })
        .await?;
    let Some(created) = created else {
        return Err(ApiError::conflict(
            "user_email_exists",
            "A user with this email already exists",
        ));
    };
    tracing::info!(
        audit = true,
        action = "create",
        resource_type = "user",
        resource_id = %created.id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        created_email = %created.email,
        "AUDIT: CREATE user"
    );
    Ok(Json(UserResponse {
        message: "User created successfully",
    }))
}

/// Delete one user. Their sessions and developer access tokens stop working
/// on the next request.
#[utoipa::path(
    delete,
    path = "/users/{user_id}",
    operation_id = "delete_user",
    tag = "auth",
    params(("user_id" = String, Path, description = "The user's identifier.")),
    responses(
        (status = 200, description = "The user was deleted.", body = UserResponse),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 404, description = "No such user.", body = ErrorResponse),
    )
)]
pub async fn delete_user(
    State(state): State<AppState>,
    user: AuthenticatedUser,
    ApiPath(user_id): ApiPath<String>,
) -> Result<Json<UserResponse>, ApiError> {
    let deleted_id = user_id.clone();
    let deleted = state
        .application_db
        .writer
        .call(move |connection| users::delete(connection, &deleted_id))
        .await?;
    if !deleted {
        return Err(ApiError::not_found("User not found"));
    }
    tracing::info!(
        audit = true,
        action = "delete",
        resource_type = "user",
        resource_id = %user_id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        "AUDIT: DELETE user"
    );
    Ok(Json(UserResponse {
        message: "User deleted successfully",
    }))
}

#[cfg(test)]
mod tests;
