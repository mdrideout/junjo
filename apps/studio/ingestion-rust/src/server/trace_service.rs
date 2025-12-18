use std::sync::Arc;

use opentelemetry_proto::tonic::collector::trace::v1::{
    trace_service_server::TraceService as OtlpTraceService,
    ExportTraceServiceRequest, ExportTraceServiceResponse,
};
use tokio::sync::{mpsc, RwLock};
use tonic::{Request, Response, Status};
use tracing::{debug, warn};

use crate::backend::BackendClient;
use crate::wal::{ArrowWal, SpanRecord};
use super::auth::ApiKeyInterceptor;
use super::backpressure::BackpressureMonitor;

/// OTLP TraceService implementation.
pub struct TraceService {
    wal: Arc<RwLock<ArrowWal>>,
    auth: ApiKeyInterceptor,
    backpressure: BackpressureMonitor,
    /// Channel to notify flusher when a WAL segment is written
    segment_notify: mpsc::Sender<()>,
}

impl TraceService {
    pub fn new(
        wal: Arc<RwLock<ArrowWal>>,
        backend: Arc<BackendClient>,
        backpressure_max_bytes: u64,
        segment_notify: mpsc::Sender<()>,
    ) -> Self {
        Self {
            wal,
            auth: ApiKeyInterceptor::new(backend),
            backpressure: BackpressureMonitor::new(backpressure_max_bytes),
            segment_notify,
        }
    }
}

#[tonic::async_trait]
impl OtlpTraceService for TraceService {
    async fn export(
        &self,
        request: Request<ExportTraceServiceRequest>,
    ) -> Result<Response<ExportTraceServiceResponse>, Status> {
        let start = std::time::Instant::now();

        // Check backpressure (fast path - just reads AtomicBool)
        if self.backpressure.is_under_pressure() {
            warn!("Request rejected due to backpressure");
            return Err(Status::resource_exhausted(
                "Server under memory pressure, please retry later",
            ));
        }

        // Validate API key
        let api_key = ApiKeyInterceptor::extract_api_key(&request)
            .ok_or_else(|| Status::unauthenticated("Missing x-junjo-api-key header"))?;

        let auth_start = std::time::Instant::now();
        let is_valid = self.auth.validate(&api_key).await?;
        let auth_duration = auth_start.elapsed();

        if !is_valid {
            warn!(api_key_prefix = &api_key[..8.min(api_key.len())], "API key validation failed");
            return Err(Status::unauthenticated("Invalid API key"));
        }

        if auth_duration.as_millis() > 100 {
            warn!(auth_ms = auth_duration.as_millis(), "Slow API key validation");
        }

        let inner = request.into_inner();

        // Convert spans to records
        let mut records = Vec::new();
        let mut span_count = 0;

        for resource_spans in &inner.resource_spans {
            let resource = resource_spans.resource.as_ref();

            for scope_spans in &resource_spans.scope_spans {
                for span in &scope_spans.spans {
                    let record = SpanRecord::from_otlp(span, resource);
                    records.push(record);
                    span_count += 1;
                }
            }
        }

        if records.is_empty() {
            return Ok(Response::new(ExportTraceServiceResponse {
                partial_success: None,
            }));
        }

        // Write to WAL
        let wal_start = std::time::Instant::now();
        {
            let mut wal = self.wal.write().await;
            let lock_acquired = wal_start.elapsed();

            let segment_written = wal.write_spans(records).map_err(|e| {
                warn!(error = %e, "Failed to write spans to WAL");
                Status::internal("Failed to write spans")
            })?;

            let write_done = wal_start.elapsed();
            if write_done.as_millis() > 5000 {
                warn!(
                    lock_ms = lock_acquired.as_millis(),
                    total_ms = write_done.as_millis(),
                    span_count = span_count,
                    "Slow WAL write"
                );
            }

            // Notify flusher reactively when a segment is written
            if segment_written {
                let _ = self.segment_notify.send(()).await;
            }
        }

        let total_duration = start.elapsed();
        if total_duration.as_millis() > 5000 {
            warn!(total_ms = total_duration.as_millis(), span_count = span_count, "Slow request");
        }

        debug!(span_count = span_count, duration_ms = total_duration.as_millis(), "Ingested spans");

        Ok(Response::new(ExportTraceServiceResponse {
            partial_success: None,
        }))
    }
}
