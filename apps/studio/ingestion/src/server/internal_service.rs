use std::path::PathBuf;
use std::sync::Arc;

use tokio::sync::RwLock;
use tonic::{Request, Response, Status};
use tracing::{debug, info, warn};

use crate::flusher::Flusher;
use crate::proto::{
    internal_ingestion_service_server::InternalIngestionService,
    FlushWalRequest, FlushWalResponse,
    PrepareHotSnapshotRequest, PrepareHotSnapshotResponse,
};
use crate::wal::ArrowWal;

/// Internal gRPC service for backend communication.
pub struct InternalService {
    wal: Arc<RwLock<ArrowWal>>,
    flusher: Arc<Flusher>,
    snapshot_path: PathBuf,
}

impl InternalService {
    pub fn new(wal: Arc<RwLock<ArrowWal>>, flusher: Arc<Flusher>, snapshot_path: PathBuf) -> Self {
        Self { wal, flusher, snapshot_path }
    }
}

#[tonic::async_trait]
impl InternalIngestionService for InternalService {
    async fn flush_wal(
        &self,
        _request: Request<FlushWalRequest>,
    ) -> Result<Response<FlushWalResponse>, Status> {
        info!("FlushWAL request received");

        match self.flusher.flush_now().await {
            Ok(()) => {
                info!("FlushWAL completed successfully");
                Ok(Response::new(FlushWalResponse {
                    success: true,
                    error_message: String::new(),
                }))
            }
            Err(e) => {
                warn!(error = %e, "FlushWAL failed");
                Ok(Response::new(FlushWalResponse {
                    success: false,
                    error_message: e.to_string(),
                }))
            }
        }
    }

    async fn prepare_hot_snapshot(
        &self,
        _request: Request<PrepareHotSnapshotRequest>,
    ) -> Result<Response<PrepareHotSnapshotResponse>, Status> {
        debug!("PrepareHotSnapshot request received");

        let start = std::time::Instant::now();

        // Create snapshot (flushes pending + copies IPC file)
        let result = {
            let mut wal = self.wal.write().await;
            wal.create_snapshot(&self.snapshot_path)
        };

        match result {
            Ok((row_count, file_size_bytes)) => {
                let duration = start.elapsed();
                info!(
                    snapshot_path = %self.snapshot_path.display(),
                    row_count = row_count,
                    file_size_bytes = file_size_bytes,
                    duration_ms = duration.as_millis(),
                    "PrepareHotSnapshot completed"
                );

                // If there is no WAL data, ArrowWal removes the prior snapshot (if any)
                // and returns (0, 0). In that case, return an empty snapshot_path so
                // callers don't try to read a non-existent file.
                let snapshot_path = if row_count == 0 && file_size_bytes == 0 {
                    String::new()
                } else {
                    self.snapshot_path.to_string_lossy().to_string()
                };

                Ok(Response::new(PrepareHotSnapshotResponse {
                    snapshot_path,
                    row_count,
                    file_size_bytes: file_size_bytes as i64,
                    success: true,
                    error_message: String::new(),
                }))
            }
            Err(e) => {
                warn!(error = %e, "PrepareHotSnapshot failed");
                Ok(Response::new(PrepareHotSnapshotResponse {
                    snapshot_path: String::new(),
                    row_count: 0,
                    file_size_bytes: 0,
                    success: false,
                    error_message: e.to_string(),
                }))
            }
        }
    }
}
