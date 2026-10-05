//! Application Telemetry API key management.

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use serde::Deserialize;
use utoipa::ToSchema;
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::error::{ApiError, ApiJson, ApiPath, ErrorResponse};
use crate::features::auth::AuthenticatedUser;
use crate::ids::{generate_api_key, generate_id};
use crate::state::AppState;
use crate::text;
use crate::timestamps::UtcSeconds;

pub mod repo;

use repo::ApiKey;

/// A human-readable key name. It must contain something other than
/// whitespace.
#[derive(Debug, Deserialize)]
#[serde(try_from = "String")]
pub struct ApiKeyName(String);

impl TryFrom<String> for ApiKeyName {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if text::trimmed(&value).is_empty() {
            return Err("API key name cannot be empty".to_string());
        }
        Ok(Self(value))
    }
}

/// This feature's routes, relative to `/api/v1`.
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(create_api_key, list_api_keys))
        .routes(routes!(delete_api_key))
}

/// The request to create an API key.
#[derive(Deserialize, ToSchema)]
#[schema(as = APIKeyCreate)]
pub struct CreateApiKeyRequest {
    /// Human-readable name for the key.
    #[schema(value_type = String, min_length = 1)]
    name: ApiKeyName,
}

/// Create an Application Telemetry API key.
///
/// Keys are a shared resource: any signed-in user may create, list, and
/// delete them.
#[utoipa::path(
    post,
    path = "/api-keys",
    operation_id = "create_api_key",
    tag = "api_keys",
    request_body = CreateApiKeyRequest,
    responses(
        (status = 201, description = "The created key.", body = ApiKey),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn create_api_key(
    State(state): State<AppState>,
    user: AuthenticatedUser,
    ApiJson(request): ApiJson<CreateApiKeyRequest>,
) -> Result<(StatusCode, Json<ApiKey>), ApiError> {
    let api_key = ApiKey {
        id: generate_id(),
        key: generate_api_key(),
        name: request.name.0,
        created_at: UtcSeconds::now(),
    };
    let stored = api_key.clone();
    state
        .application_db
        .writer
        .call(move |connection| repo::create(connection, &stored))
        .await?;
    tracing::info!(
        audit = true,
        action = "create",
        resource_type = "api_key",
        resource_id = %api_key.id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        name = %api_key.name,
        "AUDIT: CREATE api_key"
    );
    Ok((StatusCode::CREATED, Json(api_key)))
}

/// List every API key, newest first.
#[utoipa::path(
    get,
    path = "/api-keys",
    operation_id = "list_api_keys",
    tag = "api_keys",
    responses(
        (status = 200, description = "Every API key.", body = Vec<ApiKey>),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
    )
)]
pub async fn list_api_keys(
    State(state): State<AppState>,
    _user: AuthenticatedUser,
) -> Result<Json<Vec<ApiKey>>, ApiError> {
    let api_keys = state
        .application_db
        .reader
        .call(|connection| repo::list(connection))
        .await?;
    Ok(Json(api_keys))
}

/// Delete one API key.
#[utoipa::path(
    delete,
    path = "/api-keys/{id}",
    operation_id = "delete_api_key",
    tag = "api_keys",
    params(("id" = String, Path, description = "The API key's identifier.")),
    responses(
        (status = 204, description = "The key was deleted."),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 404, description = "No such key.", body = ErrorResponse),
    )
)]
pub async fn delete_api_key(
    State(state): State<AppState>,
    user: AuthenticatedUser,
    ApiPath(id): ApiPath<String>,
) -> Result<StatusCode, ApiError> {
    let deleted_id = id.clone();
    let deleted = state
        .application_db
        .writer
        .call(move |connection| repo::delete(connection, &deleted_id))
        .await?;
    if !deleted {
        return Err(ApiError::not_found("API key not found"));
    }
    tracing::info!(
        audit = true,
        action = "delete",
        resource_type = "api_key",
        resource_id = %id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        "AUDIT: DELETE api_key"
    );
    Ok(StatusCode::NO_CONTENT)
}

#[cfg(test)]
mod tests;
