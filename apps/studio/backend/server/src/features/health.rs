//! Liveness endpoint. It stays at the root, outside `/api/v1`.

use axum::Json;
use serde::Serialize;
use utoipa::ToSchema;

fn package_version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Health check response.
#[derive(Serialize, ToSchema)]
pub struct HealthResponse {
    /// Health status.
    #[schema(required = false, default = "ok")]
    status: &'static str,
    /// API version.
    #[schema(required = false, default = package_version)]
    version: &'static str,
    /// Application name.
    app_name: &'static str,
}

/// Report that the backend is running, with its version.
#[utoipa::path(
    get,
    path = "/health",
    operation_id = "health_health_get",
    tag = "Health",
    responses((status = 200, description = "The backend is running.", body = HealthResponse))
)]
pub async fn health() -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok",
        version: package_version(),
        app_name: "Junjo AI Studio",
    })
}
