use std::pin::Pin;
use std::sync::Arc;

use tokio_stream::Stream;
use tonic::{Request, Response, Status};
use tracing::{debug, error, info};
use ulid::Ulid;

use crate::backend_client::BackendClient;
use crate::proto::ingestion::internal_ingestion_service_server::InternalIngestionService;
use crate::proto::ingestion::{
    ArrowBatch, FlushWalRequest, FlushWalResponse, GetHotSpansArrowRequest,
    GetWalDistinctServiceNamesRequest, GetWalDistinctServiceNamesResponse,
    GetWalSpansArrowRequest, GetWarmCursorRequest, GetWarmCursorResponse,
    ReadSpansRequest, ReadSpansResponse,
};
use crate::storage::Repository;

/// InternalIngestionServiceImpl provides the internal gRPC API for the backend.
pub struct InternalIngestionServiceImpl {
    repository: Arc<Repository>,
    backend_client: Arc<BackendClient>,
}

impl InternalIngestionServiceImpl {
    pub fn new(repository: Arc<Repository>, backend_client: Arc<BackendClient>) -> Self {
        Self {
            repository,
            backend_client,
        }
    }
}

type ResponseStream<T> = Pin<Box<dyn Stream<Item = Result<T, Status>> + Send>>;

#[tonic::async_trait]
impl InternalIngestionService for InternalIngestionServiceImpl {
    type ReadSpansStream = ResponseStream<ReadSpansResponse>;
    type GetWALSpansArrowStream = ResponseStream<ArrowBatch>;
    type GetHotSpansArrowStream = ResponseStream<ArrowBatch>;

    async fn read_spans(
        &self,
        request: Request<ReadSpansRequest>,
    ) -> Result<Response<Self::ReadSpansStream>, Status> {
        let req = request.into_inner();

        // Parse start ULID if provided
        let since_ulid = if req.start_key_ulid.is_empty() {
            None
        } else {
            let mut bytes = [0u8; 16];
            if req.start_key_ulid.len() == 16 {
                bytes.copy_from_slice(&req.start_key_ulid);
                Some(Ulid::from_bytes(bytes))
            } else {
                return Err(Status::invalid_argument("Invalid ULID length"));
            }
        };

        // Get spans from repository
        let spans = self
            .repository
            .get_spans_since(since_ulid)
            .map_err(|e| Status::internal(format!("Failed to get spans: {}", e)))?;

        let remaining = spans.len() as u64;

        // Create stream of responses
        let stream = tokio_stream::iter(spans.into_iter().enumerate().map(
            move |(i, record)| {
                // Parse ULID from string
                let ulid: Ulid = record.ulid.parse().map_err(|_| {
                    Status::internal("Invalid ULID in span record")
                })?;

                Ok(ReadSpansResponse {
                    key_ulid: ulid.to_bytes().to_vec(),
                    span_bytes: vec![], // Not using raw proto bytes in Rust impl
                    resource_bytes: vec![],
                    remaining_count: remaining.saturating_sub(i as u64 + 1),
                })
            },
        ));

        Ok(Response::new(Box::pin(stream)))
    }

    async fn get_wal_spans_arrow(
        &self,
        request: Request<GetWalSpansArrowRequest>,
    ) -> Result<Response<Self::GetWALSpansArrowStream>, Status> {
        let _req = request.into_inner();

        // TODO: Implement Arrow IPC serialization in Phase 2
        // For now, return empty stream
        let stream = tokio_stream::empty();
        Ok(Response::new(Box::pin(stream)))
    }

    async fn get_hot_spans_arrow(
        &self,
        request: Request<GetHotSpansArrowRequest>,
    ) -> Result<Response<Self::GetHotSpansArrowStream>, Status> {
        let _req = request.into_inner();

        // TODO: Implement Arrow IPC serialization in Phase 2
        // For now, return empty stream
        let stream = tokio_stream::empty();
        Ok(Response::new(Box::pin(stream)))
    }

    async fn get_warm_cursor(
        &self,
        _request: Request<GetWarmCursorRequest>,
    ) -> Result<Response<GetWarmCursorResponse>, Status> {
        // TODO: Implement warm cursor tracking in Phase 2
        Ok(Response::new(GetWarmCursorResponse {
            last_warm_ulid: vec![],
            last_warm_time_ns: 0,
            warm_file_count: 0,
        }))
    }

    async fn get_wal_distinct_service_names(
        &self,
        _request: Request<GetWalDistinctServiceNamesRequest>,
    ) -> Result<Response<GetWalDistinctServiceNamesResponse>, Status> {
        // Get all spans and extract unique service names
        let spans = self
            .repository
            .get_all_spans()
            .map_err(|e| Status::internal(format!("Failed to get spans: {}", e)))?;

        let mut service_names: std::collections::HashSet<String> = std::collections::HashSet::new();
        for span in spans {
            service_names.insert(span.service_name);
        }

        Ok(Response::new(GetWalDistinctServiceNamesResponse {
            service_names: service_names.into_iter().collect(),
        }))
    }

    async fn flush_wal(
        &self,
        _request: Request<FlushWalRequest>,
    ) -> Result<Response<FlushWalResponse>, Status> {
        // Force flush storage
        if let Err(e) = self.repository.flush() {
            error!(error = %e, "Failed to flush storage");
            return Ok(Response::new(FlushWalResponse {
                success: false,
                error_message: e.to_string(),
            }));
        }

        // TODO: Implement Parquet flush in Phase 2
        info!("Manual flush triggered");

        Ok(Response::new(FlushWalResponse {
            success: true,
            error_message: String::new(),
        }))
    }
}
