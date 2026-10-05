//! Deployment facts the UI shows to a user setting up an SDK.

use axum::Json;
use axum::extract::State;
use serde::Serialize;
use utoipa::ToSchema;
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::state::AppState;

/// Runtime configuration the UI needs to display.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct ConfigResponse {
    /// Current environment (development/production)
    pub environment: &'static str,
    /// OTLP ingestion endpoint for OpenTelemetry SDKs
    pub otlp_endpoint: String,
}

/// This feature's routes, relative to `/api/v1`.
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(get_config))
}

/// Get runtime configuration.
///
/// Public: it reports only where SDKs send telemetry and which environment
/// this deployment runs in.
#[utoipa::path(
    get,
    path = "/config",
    operation_id = "get_config",
    tag = "Configuration",
    responses((status = 200, description = "The deployment's configuration.", body = ConfigResponse))
)]
pub async fn get_config(State(state): State<AppState>) -> Json<ConfigResponse> {
    Json(state.deployment.as_ref().clone())
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use serde_json::json;

    use crate::test_http::{app, get, send};

    #[tokio::test]
    async fn the_configuration_is_public_and_names_the_otlp_endpoint() {
        let (router, _app) = app();
        let reply = send(&router, get("/api/v1/config", None)).await;
        assert_eq!(reply.status, StatusCode::OK);
        assert_eq!(
            reply.body,
            json!({
                "environment": "development",
                "otlp_endpoint": "grpc://localhost:26155",
            })
        );
    }
}
