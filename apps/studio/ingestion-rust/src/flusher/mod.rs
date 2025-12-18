use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

use tokio::sync::{mpsc, RwLock};
use tokio::time::interval;
use tracing::{debug, error, info, warn};

use crate::backend::BackendClient;
use crate::wal::ArrowWal;

/// Manages background flushing of WAL to Parquet files.
pub struct Flusher {
    wal: Arc<RwLock<ArrowWal>>,
    output_dir: PathBuf,
    max_bytes: u64,
    max_age_secs: u64,
    backend: Arc<BackendClient>,
    last_flush: RwLock<Instant>,
}

impl Flusher {
    pub fn new(
        wal: Arc<RwLock<ArrowWal>>,
        output_dir: PathBuf,
        max_bytes: u64,
        max_age_secs: u64,
        backend: Arc<BackendClient>,
    ) -> Self {
        Self {
            wal,
            output_dir,
            max_bytes,
            max_age_secs,
            backend,
            last_flush: RwLock::new(Instant::now()),
        }
    }

    /// Run the flusher loop in the background.
    /// Takes the segment notification receiver for reactive flush triggering.
    pub async fn run(&self, mut segment_rx: mpsc::Receiver<()>) {
        let mut check_interval = interval(Duration::from_secs(10));
        let mut pending_flush_interval = interval(Duration::from_secs(3));

        loop {
            tokio::select! {
                // Reactive: triggered when TraceService writes a new WAL segment
                _ = segment_rx.recv() => {
                    if let Err(e) = self.check_and_flush().await {
                        error!(error = %e, "Error during reactive flush check");
                    }
                }
                // Fallback: periodic check for age-based flush
                _ = check_interval.tick() => {
                    if let Err(e) = self.check_and_flush().await {
                        error!(error = %e, "Error during periodic flush check");
                    }
                }
                // Durability: flush pending spans to IPC segments
                _ = pending_flush_interval.tick() => {
                    if let Err(e) = self.flush_pending_to_ipc().await {
                        error!(error = %e, "Error during pending flush");
                    }
                }
            }
        }
    }

    /// Flush any pending spans to IPC segments (for durability).
    async fn flush_pending_to_ipc(&self) -> anyhow::Result<()> {
        let mut wal = self.wal.write().await;
        if wal.needs_timer_flush() {
            debug!("Timer-based flush of pending spans to IPC");
            wal.flush_pending()?;
        }
        Ok(())
    }

    /// Check if flush is needed and perform it.
    async fn check_and_flush(&self) -> anyhow::Result<()> {
        let file_size = {
            let wal = self.wal.read().await;
            wal.file_size()
        };

        let last_flush = *self.last_flush.read().await;
        let age = last_flush.elapsed();

        // Check byte threshold
        if file_size >= self.max_bytes {
            info!(
                file_size_mb = file_size / 1024 / 1024,
                threshold_mb = self.max_bytes / 1024 / 1024,
                "Flush triggered by size threshold"
            );
            return self.do_flush().await;
        }

        // Check age threshold
        if age.as_secs() >= self.max_age_secs && file_size > 0 {
            info!(
                age_secs = age.as_secs(),
                threshold_secs = self.max_age_secs,
                "Flush triggered by age threshold"
            );
            return self.do_flush().await;
        }

        debug!(
            file_size_mb = file_size / 1024 / 1024,
            age_secs = age.as_secs(),
            "No flush needed"
        );

        Ok(())
    }

    /// Trigger an immediate flush.
    pub async fn flush_now(&self) -> anyhow::Result<()> {
        self.do_flush().await
    }

    /// Perform the actual flush operation.
    async fn do_flush(&self) -> anyhow::Result<()> {
        let start = Instant::now();

        // Generate output path with date partitioning
        let now = chrono::Utc::now();
        let output_path = self.output_dir
            .join(format!("year={}", now.format("%Y")))
            .join(format!("month={}", now.format("%m")))
            .join(format!("day={}", now.format("%d")))
            .join(format!(
                "{}_{}.parquet",
                now.format("%Y%m%d_%H%M%S"),
                rand_suffix()
            ));

        // Streaming flush: reads one segment at a time, writes to parquet, drops memory
        let row_count = {
            let mut wal = self.wal.write().await;
            wal.flush_to_parquet(&output_path)?
        };

        if row_count == 0 {
            debug!("No data to flush");
            return Ok(());
        }

        // Notify backend (fire-and-forget to avoid blocking the flusher)
        let output_path_str = output_path.to_string_lossy().to_string();
        let backend = Arc::clone(&self.backend);
        tokio::spawn(async move {
            if let Err(e) = backend.notify_new_parquet(&output_path_str).await {
                warn!(error = %e, path = %output_path_str, "Failed to notify backend of new parquet file");
            }
        });

        // Note: segment deletion now happens inside flush_to_parquet()
        // which deletes only the segments it flushed (preserving new ones)

        // Update last flush time
        *self.last_flush.write().await = Instant::now();

        let duration = start.elapsed();
        info!(
            rows = row_count,
            path = %output_path.display(),
            duration_ms = duration.as_millis(),
            "Flush completed"
        );

        Ok(())
    }
}

fn rand_suffix() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .subsec_nanos();
    format!("{:08x}", nanos)
}
