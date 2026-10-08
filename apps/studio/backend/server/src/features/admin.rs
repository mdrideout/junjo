//! Operator actions.

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use serde::Serialize;
use utoipa::ToSchema;
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::error::{ApiError, ErrorResponse};
use crate::features::auth::AuthenticatedUser;
use crate::state::AppState;

/// The result of a write-ahead log flush.
#[derive(Debug, Serialize, ToSchema)]
#[schema(as = FlushWALResponse)]
pub struct FlushWalResult {
    #[schema(examples(true))]
    success: bool,
    #[schema(examples("WAL flush completed"))]
    message: String,
    /// How many of the flushed files were indexed before this response.
    #[schema(value_type = i64, required = false, default = 0, examples(1))]
    files_indexed: usize,
}

fn failed(code: &'static str, message: &'static str) -> ApiError {
    ApiError::new(StatusCode::INTERNAL_SERVER_ERROR, code, message)
}

/// This feature's routes, relative to `/api/v1`.
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(flush_wal))
}

/// Flush ingestion's write-ahead log to cold Parquet files and index them.
///
/// Spans normally become cold files when the log fills. This makes them cold,
/// and indexed, now.
#[utoipa::path(
    post,
    path = "/admin/flush-wal",
    operation_id = "flush_wal",
    tag = "admin",
    responses(
        (status = 200, description = "The log was flushed and its files indexed.", body = FlushWalResult),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 500, description = "The flush or the indexing failed.", body = ErrorResponse),
    )
)]
pub async fn flush_wal(
    State(state): State<AppState>,
    user: AuthenticatedUser,
) -> Result<Json<FlushWalResult>, ApiError> {
    state.ingestion.flush_wal().await.map_err(|error| {
        tracing::error!(%error, "WAL flush failed");
        failed("wal_flush_failed", "WAL flush failed")
    })?;
    let files_indexed = state.indexer.index_now().await.map_err(|error| {
        tracing::error!(%error, "indexing after the WAL flush failed");
        failed(
            "post_flush_indexing_failed",
            "WAL flush completed, but indexing its files failed",
        )
    })?;
    tracing::info!(
        audit = true,
        action = "flush_wal",
        resource_type = "wal",
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        files_indexed,
        "AUDIT: FLUSH_WAL wal"
    );
    Ok(Json(FlushWalResult {
        success: true,
        message: format!("WAL flush completed, {files_indexed} file(s) indexed"),
        files_indexed,
    }))
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use serde_json::json;

    use crate::app::router;
    use crate::test_http::{get, post, send, sign_up};
    use crate::test_support::{TestSpan, ingestion_flushing, test_app};

    const FLUSH: &str = "/api/v1/admin/flush-wal";

    #[tokio::test]
    async fn a_flush_indexes_the_flushed_files_before_it_answers() {
        let mut app = test_app();
        let indexer = app.spawn_indexer();
        app.state.ingestion = ingestion_flushing(Ok(())).await;
        let router = router(app.state.clone(), false);
        let cookie = sign_up(&router).await;
        // What the flush leaves behind: cold files the index has not seen.
        app.write_cold_file(
            "a.parquet",
            &[TestSpan::new("trace-1", "span-1", "checkout")],
        );
        app.write_cold_file(
            "b.parquet",
            &[TestSpan::new("trace-2", "span-2", "billing")],
        );

        let flushed = send(&router, post(FLUSH, Some(&cookie), json!({}))).await;
        assert_eq!(flushed.status, StatusCode::OK, "{}", flushed.body);
        assert_eq!(
            flushed.body,
            json!({
                "success": true,
                "message": "WAL flush completed, 2 file(s) indexed",
                "files_indexed": 2,
            })
        );
        // The index already covers them.
        let services = send(
            &router,
            get("/api/v1/observability/services", Some(&cookie)),
        )
        .await;
        assert_eq!(services.body, json!(["billing", "checkout"]));

        let again = send(&router, post(FLUSH, Some(&cookie), json!({}))).await;
        assert_eq!(again.body["files_indexed"], 0);

        (indexer.shutdown_sender())();
        indexer.finished.await.unwrap();
    }

    #[tokio::test]
    async fn a_failed_flush_is_an_error_and_indexes_nothing() {
        let mut app = test_app();
        let indexer = app.spawn_indexer();
        let router = router(app.state.clone(), false);
        let cookie = sign_up(&router).await;
        app.write_cold_file(
            "a.parquet",
            &[TestSpan::new("trace-1", "span-1", "checkout")],
        );
        let failed = json!({"code": "wal_flush_failed", "message": "WAL flush failed"});

        // Ingestion cannot be reached.
        let unreachable = send(&router, post(FLUSH, Some(&cookie), json!({}))).await;
        assert_eq!(unreachable.status, StatusCode::INTERNAL_SERVER_ERROR);
        assert_eq!(unreachable.body, failed);

        // Ingestion reports that the flush failed.
        app.state.ingestion = ingestion_flushing(Err("disk full")).await;
        let router = crate::app::router(app.state.clone(), false);
        let refused = send(&router, post(FLUSH, Some(&cookie), json!({}))).await;
        assert_eq!(refused.status, StatusCode::INTERNAL_SERVER_ERROR);
        assert_eq!(refused.body, failed);

        let services = send(
            &router,
            get("/api/v1/observability/services", Some(&cookie)),
        )
        .await;
        assert_eq!(services.body, json!([]));
        (indexer.shutdown_sender())();
        indexer.finished.await.unwrap();
    }

    #[tokio::test]
    async fn a_flush_whose_files_cannot_be_indexed_says_so() {
        // No indexer thread is running.
        let mut app = test_app();
        app.state.ingestion = ingestion_flushing(Ok(())).await;
        let router = router(app.state.clone(), false);
        let cookie = sign_up(&router).await;

        let reply = send(&router, post(FLUSH, Some(&cookie), json!({}))).await;
        assert_eq!(reply.status, StatusCode::INTERNAL_SERVER_ERROR);
        assert_eq!(
            reply.body,
            json!({
                "code": "post_flush_indexing_failed",
                "message": "WAL flush completed, but indexing its files failed",
            })
        );
    }
}
