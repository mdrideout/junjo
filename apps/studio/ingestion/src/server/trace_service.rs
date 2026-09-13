use std::sync::Arc;

use opentelemetry_proto::tonic::collector::trace::v1::{
    trace_service_server::TraceService as OtlpTraceService, ExportTraceServiceRequest,
    ExportTraceServiceResponse,
};
use tokio::sync::{mpsc, RwLock};
use tonic::{Request, Response, Status};
use tracing::{debug, warn};

use super::auth::{ApiKeyAuthConfig, ApiKeyInterceptor};
use super::backpressure::BackpressureMonitor;
use crate::backend::BackendClient;
use crate::wal::{ArrowWal, SpanRecord};

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
        auth_config: ApiKeyAuthConfig,
        backpressure_max_bytes: u64,
        segment_notify: mpsc::Sender<()>,
    ) -> Self {
        Self {
            wal,
            auth: ApiKeyInterceptor::new(backend, auth_config),
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
            debug!("Request rejected due to backpressure");
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
            debug!("API key validation failed");
            return Err(Status::unauthenticated("Invalid API key"));
        }

        if auth_duration.as_millis() > 5000 {
            warn!(
                auth_ms = auth_duration.as_millis(),
                "Slow API key validation"
            );
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

            // The receiver needs WAL access to drain a full notification queue.
            drop(wal);

            // Notify flusher reactively when a segment is written
            if segment_written {
                let _ = self.segment_notify.send(()).await;
            }
        }

        let total_duration = start.elapsed();
        if total_duration.as_millis() > 5000 {
            warn!(
                total_ms = total_duration.as_millis(),
                span_count = span_count,
                "Slow request"
            );
        }

        debug!(
            span_count = span_count,
            duration_ms = total_duration.as_millis(),
            "Ingested spans"
        );

        Ok(Response::new(ExportTraceServiceResponse {
            partial_success: None,
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flusher::Flusher;
    use crate::proto::{
        internal_auth_service_server::{InternalAuthService, InternalAuthServiceServer},
        ValidateApiKeyRequest, ValidateApiKeyResponse,
    };
    use crate::recent_cold_files::RecentColdFiles;
    use opentelemetry_proto::tonic::trace::v1::{ResourceSpans, ScopeSpans, Span};
    use std::sync::Mutex;
    use std::time::Duration;
    use tokio_stream::wrappers::TcpListenerStream;

    struct TestAuth;
    #[tonic::async_trait]
    impl InternalAuthService for TestAuth {
        async fn validate_api_key(
            &self,
            _: Request<ValidateApiKeyRequest>,
        ) -> Result<Response<ValidateApiKeyResponse>, Status> {
            Ok(Response::new(ValidateApiKeyResponse { is_valid: true }))
        }
    }
    fn export_request(span_count: usize) -> Request<ExportTraceServiceRequest> {
        let mut request = Request::new(ExportTraceServiceRequest {
            resource_spans: vec![ResourceSpans {
                scope_spans: vec![ScopeSpans {
                    spans: vec![Span::default(); span_count],
                    ..Default::default()
                }],
                ..Default::default()
            }],
        });
        request
            .metadata_mut()
            .insert("x-junjo-api-key", "test-key".parse().unwrap());
        request
    }

    #[tokio::test]
    async fn full_notification_queue_releases_wal_and_shutdown_persists_tail() {
        use std::future::{poll_fn, Future};
        use std::task::Poll;

        let dir = tempfile::tempdir().unwrap();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let backend_addr = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            tonic::transport::Server::builder()
                .add_service(InternalAuthServiceServer::new(TestAuth))
                .serve_with_incoming(TcpListenerStream::new(listener))
                .await
        });
        let wal_path = dir.path().join("wal");
        let wal = Arc::new(RwLock::new(ArrowWal::new(&wal_path, 1000).unwrap()));
        let (segment_tx, segment_rx) = mpsc::channel(16);
        let service = TraceService::new(
            wal.clone(),
            Arc::new(
                BackendClient::new(
                    format!("http://{backend_addr}"),
                    "test-internal-grpc-token-32-bytes-long".into(),
                    Duration::from_secs(2),
                )
                .unwrap(),
            ),
            ApiKeyAuthConfig {
                positive_cache_ttl: Duration::from_secs(30),
                positive_cache_max_entries: 1024,
                max_concurrent_refreshes: 8,
                max_pending_requests: 32,
                validation_timeout: Duration::from_secs(2),
            },
            u64::MAX,
            segment_tx,
        );
        // Simulate a flusher busy with earlier work: fill the production-size
        // queue using real exports before allowing the receiver to run.
        for _ in 0..16 {
            service.export(export_request(1000)).await.unwrap();
        }
        let mut blocked_export = Box::pin(service.export(export_request(1001)));
        poll_fn(|cx| {
            assert!(blocked_export.as_mut().poll(cx).is_pending());
            Poll::Ready(())
        })
        .await;
        // This assertion fails immediately with the old lock scope, without
        // needing a timeout or relying on scheduler timing to detect deadlock.
        assert!(
            wal.try_write().is_ok(),
            "notification wait retained WAL lock"
        );
        let flusher = Flusher::new(
            wal.clone(),
            dir.path().join("parquet"),
            u64::MAX,
            u64::MAX,
            Arc::new(Mutex::new(RecentColdFiles::new(
                10,
                Duration::from_secs(60),
            ))),
        );
        let flusher_task = tokio::spawn(async move { flusher.run(segment_rx).await });
        blocked_export.await.unwrap();
        drop(service);
        flusher_task.await.unwrap().unwrap();
        drop(wal);
        let mut recovered = ArrowWal::new(&wal_path, 1000).unwrap();
        assert_eq!(
            recovered
                .read_batches()
                .unwrap()
                .iter()
                .map(|batch| batch.num_rows())
                .sum::<usize>(),
            17_001,
        );
        server.abort();
    }
}
