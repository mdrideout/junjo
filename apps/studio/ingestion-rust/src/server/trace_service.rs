use std::sync::Arc;

use tonic::{Request, Response, Status};
use tracing::{debug, error, info};

use crate::proto::opentelemetry::proto::collector::trace::v1::trace_service_server::TraceService;
use crate::proto::opentelemetry::proto::collector::trace::v1::{
    ExportTraceServiceRequest, ExportTraceServiceResponse,
};
use crate::proto::opentelemetry::proto::resource::v1::Resource;
use crate::proto::opentelemetry::proto::trace::v1::Span;
use crate::storage::Repository;

/// OtlpTraceService implements the OpenTelemetry TraceService for span ingestion.
pub struct OtlpTraceService {
    repository: Arc<Repository>,
}

impl OtlpTraceService {
    pub fn new(repository: Arc<Repository>) -> Self {
        Self { repository }
    }
}

#[tonic::async_trait]
impl TraceService for OtlpTraceService {
    async fn export(
        &self,
        request: Request<ExportTraceServiceRequest>,
    ) -> Result<Response<ExportTraceServiceResponse>, Status> {
        let req = request.into_inner();

        // Collect all spans with their resources
        let mut spans_to_write: Vec<(Span, Resource)> = Vec::new();

        for resource_spans in req.resource_spans {
            let resource = resource_spans.resource.unwrap_or_default();

            for scope_spans in resource_spans.scope_spans {
                for span in scope_spans.spans {
                    spans_to_write.push((span, resource.clone()));
                }
            }
        }

        if spans_to_write.is_empty() {
            debug!("Received empty export request");
            return Ok(Response::new(ExportTraceServiceResponse {
                partial_success: None,
            }));
        }

        let span_count = spans_to_write.len();

        // Write spans to storage
        match self.repository.write_spans(&spans_to_write) {
            Ok(ulids) => {
                debug!(count = ulids.len(), "Wrote spans to storage");
                Ok(Response::new(ExportTraceServiceResponse {
                    partial_success: None,
                }))
            }
            Err(e) => {
                error!(error = %e, count = span_count, "Failed to write spans");
                Err(Status::internal(format!("Failed to write spans: {}", e)))
            }
        }
    }
}
