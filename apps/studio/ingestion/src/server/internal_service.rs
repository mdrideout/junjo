use std::path::PathBuf;
use std::sync::Arc;
use std::sync::Mutex as StdMutex;
use std::time::{Duration, Instant};

use tokio::sync::{Mutex, RwLock};
use tonic::{Request, Response, Status};
use tracing::{debug, info, warn};

use crate::flusher::Flusher;
use crate::proto::{
    internal_ingestion_service_server::InternalIngestionService, FlushWalRequest, FlushWalResponse,
    PrepareHotSnapshotRequest, PrepareHotSnapshotResponse,
};
use crate::recent_cold_files::RecentColdFiles;
use crate::wal::ArrowWal;

struct _SnapshotCacheEntry {
    expires_at: Instant,
    snapshot_path: String,
    row_count: i64,
    file_size_bytes: i64,
}

/// Internal gRPC service for backend communication.
pub struct InternalService {
    wal: Arc<RwLock<ArrowWal>>,
    flusher: Arc<Flusher>,
    snapshot_path: PathBuf,
    recent_cold: Arc<StdMutex<RecentColdFiles>>,
    snapshot_cache: Mutex<Option<_SnapshotCacheEntry>>,
    snapshot_cache_ttl: Duration,
}

impl InternalService {
    pub fn new(
        wal: Arc<RwLock<ArrowWal>>,
        flusher: Arc<Flusher>,
        snapshot_path: PathBuf,
        recent_cold: Arc<StdMutex<RecentColdFiles>>,
        snapshot_cache_ttl: Duration,
    ) -> Self {
        Self {
            wal,
            flusher,
            snapshot_path,
            recent_cold,
            snapshot_cache: Mutex::new(None),
            snapshot_cache_ttl,
        }
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

        let start = Instant::now();

        // Serialize snapshot creation and apply a short TTL cache to avoid stampedes.
        let mut cache = self.snapshot_cache.lock().await;

        let cached = cache
            .as_ref()
            .filter(|entry| entry.expires_at > Instant::now())
            .map(|entry| {
                (
                    entry.snapshot_path.clone(),
                    entry.row_count,
                    entry.file_size_bytes,
                )
            });

        let (snapshot_path, row_count, file_size_bytes, success, error_message) =
            if let Some((snapshot_path, row_count, file_size_bytes)) = cached {
                (
                    snapshot_path,
                    row_count,
                    file_size_bytes,
                    true,
                    String::new(),
                )
            } else {
                // Create snapshot (flushes pending + copies IPC file)
                let result = {
                    let mut wal = self.wal.write().await;
                    wal.create_snapshot(&self.snapshot_path)
                };

                match result {
                    Ok((row_count, file_size_bytes_u64)) => {
                        let file_size_bytes = file_size_bytes_u64 as i64;

                        // If there is no WAL data, ArrowWal removes the prior snapshot (if any)
                        // and returns (0, 0). In that case, return an empty snapshot_path so
                        // callers don't try to read a non-existent file.
                        let snapshot_path = if row_count == 0 && file_size_bytes == 0 {
                            String::new()
                        } else {
                            self.snapshot_path.to_string_lossy().to_string()
                        };

                        // Cache only non-empty snapshots. Caching an empty snapshot can
                        // hide brand-new WAL data written shortly after a period of idleness.
                        if !self.snapshot_cache_ttl.is_zero()
                            && row_count > 0
                            && file_size_bytes > 0
                        {
                            *cache = Some(_SnapshotCacheEntry {
                                expires_at: Instant::now() + self.snapshot_cache_ttl,
                                snapshot_path: snapshot_path.clone(),
                                row_count,
                                file_size_bytes,
                            });
                        } else {
                            *cache = None;
                        }

                        (
                            snapshot_path,
                            row_count,
                            file_size_bytes,
                            true,
                            String::new(),
                        )
                    }
                    Err(e) => {
                        warn!(error = %e, "PrepareHotSnapshot failed");
                        (String::new(), 0, 0, false, e.to_string())
                    }
                }
            };

        drop(cache);

        let recent_cold_paths = {
            let mut recent = self.recent_cold.lock().expect("recent_cold mutex poisoned");
            recent.list()
        };

        let duration = start.elapsed();
        if success {
            info!(
                snapshot_path = %self.snapshot_path.display(),
                row_count = row_count,
                file_size_bytes = file_size_bytes,
                duration_ms = duration.as_millis(),
                recent_cold_paths = recent_cold_paths.len(),
                "PrepareHotSnapshot completed"
            );
        }

        Ok(Response::new(PrepareHotSnapshotResponse {
            snapshot_path,
            row_count,
            file_size_bytes,
            success,
            error_message,
            recent_cold_paths,
        }))
    }
}
