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
    /// Shared workload token for internal backend/ingestion RPCs.
    pub internal_grpc_token: String,
    /// Fixed positive-validation cache TTL. Zero disables positive reuse.
    pub api_key_cache_ttl_secs: u64,
    /// Maximum number of successful API-key validations retained in memory.
    pub api_key_cache_max_entries: usize,
    /// Maximum number of distinct authoritative backend validations in flight.
    pub api_key_validation_max_concurrency: usize,
    /// Maximum number of decoded OTLP requests waiting for a cold validation.
    pub api_key_validation_max_pending: usize,
    /// Hard deadline for an authoritative backend validation.
    pub api_key_validation_timeout_ms: u64,
    /// Log level
    pub log_level: String,

    /// Max number of recently flushed cold Parquet files to return from PrepareHotSnapshot.
    pub recent_cold_max_files: usize,
    /// Max age (seconds) for recently flushed cold Parquet files to return from PrepareHotSnapshot.
    pub recent_cold_max_age_secs: u64,
    /// Cache TTL (milliseconds) for PrepareHotSnapshot results (snapshot only).
    /// This throttles snapshot creation under concurrent UI requests.
    pub prepare_hot_snapshot_cache_ttl_ms: u64,
}

#[cfg(test)]
mod tests {
    use super::{bounded_value, Config};
    use std::env;

    #[test]
    fn defaults_use_junjo_local_port_model() {
        let old_grpc_port = env::var("GRPC_PORT").ok();
        let old_internal_grpc_port = env::var("INTERNAL_GRPC_PORT").ok();
        let old_backend_grpc_port = env::var("BACKEND_GRPC_PORT").ok();
        let old_internal_grpc_token = env::var("JUNJO_INTERNAL_GRPC_TOKEN").ok();
        let auth_variables = [
            "JUNJO_API_KEY_CACHE_TTL_SECONDS",
            "JUNJO_API_KEY_CACHE_MAX_ENTRIES",
            "JUNJO_API_KEY_VALIDATION_MAX_CONCURRENCY",
            "JUNJO_API_KEY_VALIDATION_MAX_PENDING",
            "JUNJO_API_KEY_VALIDATION_TIMEOUT_MS",
        ];
        let old_auth_values: Vec<_> = auth_variables
            .iter()
            .map(|name| (name, env::var(name).ok()))
            .collect();

        env::remove_var("GRPC_PORT");
        env::remove_var("INTERNAL_GRPC_PORT");
        env::remove_var("BACKEND_GRPC_PORT");
        for name in auth_variables {
            env::remove_var(name);
        }
        env::set_var(
            "JUNJO_INTERNAL_GRPC_TOKEN",
            "test-internal-grpc-token-32-bytes-long",
        );

        let config = Config::from_env();
        assert_eq!(config.grpc_port, 26155);
        assert_eq!(config.internal_grpc_port, 50052);
        assert_eq!(config.backend_port, 50053);
        assert_eq!(config.api_key_cache_ttl_secs, 10);
        assert_eq!(config.api_key_cache_max_entries, 1024);
        assert_eq!(config.api_key_validation_max_concurrency, 8);
        assert_eq!(config.api_key_validation_max_pending, 32);
        assert_eq!(config.api_key_validation_timeout_ms, 2000);

        match old_grpc_port {
            Some(value) => env::set_var("GRPC_PORT", value),
            None => env::remove_var("GRPC_PORT"),
        }
        match old_internal_grpc_port {
            Some(value) => env::set_var("INTERNAL_GRPC_PORT", value),
            None => env::remove_var("INTERNAL_GRPC_PORT"),
        }
        match old_backend_grpc_port {
            Some(value) => env::set_var("BACKEND_GRPC_PORT", value),
            None => env::remove_var("BACKEND_GRPC_PORT"),
        }
        match old_internal_grpc_token {
            Some(value) => env::set_var("JUNJO_INTERNAL_GRPC_TOKEN", value),
            None => env::remove_var("JUNJO_INTERNAL_GRPC_TOKEN"),
        }
        for (name, old_value) in old_auth_values {
            match old_value {
                Some(value) => env::set_var(name, value),
                None => env::remove_var(name),
            }
        }
    }

    #[test]
    fn bounded_auth_settings_reject_unsafe_values() {
        assert_eq!(bounded_value("TEST", Some("0"), 10, 0, 30), 0);
        assert_eq!(bounded_value("TEST", Some("30"), 10, 0, 30), 30);

        let too_large = std::panic::catch_unwind(|| bounded_value("TEST", Some("31"), 10, 0, 30));
        assert!(too_large.is_err());

        let malformed =
            std::panic::catch_unwind(|| bounded_value("TEST", Some("seconds"), 10, 0, 30));
        assert!(malformed.is_err());
    }
}

fn bounded_value(name: &str, raw: Option<&str>, default: u64, min: u64, max: u64) -> u64 {
    let value = raw.map_or(default, |raw_value| {
        raw_value
            .parse::<u64>()
            .unwrap_or_else(|_| panic!("{name} must be an integer between {min} and {max}"))
    });
    assert!(
        (min..=max).contains(&value),
        "{name} must be between {min} and {max}"
    );
    value
}

fn bounded_env(name: &str, default: u64, min: u64, max: u64) -> u64 {
    let raw = env::var(name).ok();
    bounded_value(name, raw.as_deref(), default, min, max)
}

impl Config {
    /// Load configuration from environment variables with defaults.
    pub fn from_env() -> Self {
        let home_dir = directories::BaseDirs::new()
            .map(|d| d.home_dir().to_path_buf())
            .unwrap_or_else(|| PathBuf::from("/tmp"));

        let default_wal_dir = home_dir.join(".junjo").join("spans").join("wal");
        let default_snapshot_path = home_dir
            .join(".junjo")
            .join("spans")
            .join("hot_snapshot.parquet");
        let default_parquet_dir = home_dir.join(".junjo").join("spans").join("parquet");

        Config {
            grpc_port: env::var("GRPC_PORT")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(26155),

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

            backend_host: env::var("BACKEND_GRPC_HOST").unwrap_or_else(|_| "localhost".to_string()),

            backend_port: env::var("BACKEND_GRPC_PORT")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(50053),

            internal_grpc_token: env::var("JUNJO_INTERNAL_GRPC_TOKEN")
                .ok()
                .filter(|value| value.len() >= 32)
                .expect("JUNJO_INTERNAL_GRPC_TOKEN must contain at least 32 characters"),

            api_key_cache_ttl_secs: bounded_env("JUNJO_API_KEY_CACHE_TTL_SECONDS", 10, 0, 30),

            api_key_cache_max_entries: bounded_env(
                "JUNJO_API_KEY_CACHE_MAX_ENTRIES",
                1024,
                1,
                10_000,
            ) as usize,

            api_key_validation_max_concurrency: bounded_env(
                "JUNJO_API_KEY_VALIDATION_MAX_CONCURRENCY",
                8,
                1,
                64,
            ) as usize,

            api_key_validation_max_pending: bounded_env(
                "JUNJO_API_KEY_VALIDATION_MAX_PENDING",
                32,
                1,
                256,
            ) as usize,

            api_key_validation_timeout_ms: bounded_env(
                "JUNJO_API_KEY_VALIDATION_TIMEOUT_MS",
                2000,
                100,
                10_000,
            ),

            log_level: env::var("JUNJO_LOG_LEVEL").unwrap_or_else(|_| "info".to_string()),

            recent_cold_max_files: env::var("RECENT_COLD_MAX_FILES")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(20),

            recent_cold_max_age_secs: env::var("RECENT_COLD_MAX_AGE_SECS")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(120),

            prepare_hot_snapshot_cache_ttl_ms: env::var("PREPARE_HOT_SNAPSHOT_CACHE_TTL_MS")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(1000),
        }
    }

    /// Get backend address as a string.
    pub fn backend_addr(&self) -> String {
        format!("http://{}:{}", self.backend_host, self.backend_port)
    }
}
