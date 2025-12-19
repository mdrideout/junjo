use std::env;
use std::path::PathBuf;

/// Configuration for the ingestion service.
#[derive(Debug, Clone)]
pub struct Config {
    /// Public gRPC port for OTLP ingestion
    pub grpc_port: u16,
    /// Internal gRPC port for backend queries
    pub internal_grpc_port: u16,
    /// Directory for Arrow IPC WAL segment files
    pub wal_dir: PathBuf,
    /// Path to hot snapshot file (stable copy for backend reads)
    pub snapshot_path: PathBuf,
    /// Directory for Parquet output files
    pub parquet_output_dir: PathBuf,
    /// Flush threshold in bytes (when total WAL size exceeds this, flush to Parquet)
    pub flush_max_bytes: u64,
    /// Max age before flush in seconds
    pub flush_max_age_secs: u64,
    /// Spans per IPC segment (each segment is one batch)
    pub batch_size: usize,
    /// Memory threshold for backpressure in bytes
    pub backpressure_max_bytes: u64,
    /// Backend gRPC host
    pub backend_host: String,
    /// Backend gRPC port
    pub backend_port: u16,
    /// Log level
    pub log_level: String,
}

impl Config {
    /// Load configuration from environment variables with defaults.
    pub fn from_env() -> Self {
        let home_dir = directories::BaseDirs::new()
            .map(|d| d.home_dir().to_path_buf())
            .unwrap_or_else(|| PathBuf::from("/tmp"));

        let default_wal_dir = home_dir.join(".junjo").join("spans").join("wal");
        let default_snapshot_path = home_dir.join(".junjo").join("spans").join("hot_snapshot.parquet");
        let default_parquet_dir = home_dir.join(".junjo").join("spans").join("parquet");

        Config {
            grpc_port: env::var("GRPC_PORT")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(50051),

            internal_grpc_port: env::var("INTERNAL_GRPC_PORT")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(50052),

            wal_dir: env::var("WAL_DIR")
                .map(PathBuf::from)
                .unwrap_or(default_wal_dir),

            snapshot_path: env::var("SNAPSHOT_PATH")
                .map(PathBuf::from)
                .unwrap_or(default_snapshot_path),

            parquet_output_dir: env::var("PARQUET_OUTPUT_DIR")
                .map(PathBuf::from)
                .unwrap_or(default_parquet_dir),

            flush_max_bytes: env::var("FLUSH_MAX_MB")
                .ok()
                .and_then(|s| s.parse::<u64>().ok())
                .map(|mb| mb * 1024 * 1024)
                .unwrap_or(25 * 1024 * 1024), // 25 MB

            flush_max_age_secs: env::var("FLUSH_MAX_AGE_SECS")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(3600), // 1 hour

            batch_size: env::var("BATCH_SIZE")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(1000), // 1000 spans per segment

            backpressure_max_bytes: env::var("BACKPRESSURE_MAX_MB")
                .ok()
                .and_then(|s| s.parse::<u64>().ok())
                .map(|mb| mb * 1024 * 1024)
                .unwrap_or(300 * 1024 * 1024), // 300 MB

            backend_host: env::var("BACKEND_GRPC_HOST")
                .unwrap_or_else(|_| "localhost".to_string()),

            backend_port: env::var("BACKEND_GRPC_PORT")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(50053),

            log_level: env::var("JUNJO_LOG_LEVEL")
                .unwrap_or_else(|_| "info".to_string()),
        }
    }

    /// Get backend address as a string.
    pub fn backend_addr(&self) -> String {
        format!("http://{}:{}", self.backend_host, self.backend_port)
    }
}
