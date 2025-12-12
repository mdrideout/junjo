use std::env;
use std::path::PathBuf;
use std::time::Duration;

/// Main configuration for the ingestion service.
#[derive(Clone, Debug)]
pub struct Config {
    pub storage: StorageConfig,
    pub flusher: FlusherConfig,
    pub server: ServerConfig,
    pub backend: BackendConfig,
    pub auth: AuthConfig,
    pub log: LogConfig,
}

/// Storage configuration for fjall.
#[derive(Clone, Debug)]
pub struct StorageConfig {
    /// Path to fjall database directory
    pub wal_path: PathBuf,
}

/// Flusher configuration for Parquet output.
#[derive(Clone, Debug)]
pub struct FlusherConfig {
    /// Output directory for Parquet files
    pub output_dir: PathBuf,
    /// Interval to check flush conditions
    pub interval: Duration,
    /// Maximum age before forcing flush
    pub max_age: Duration,
    /// Maximum row count before flush
    pub max_rows: i64,
    /// Minimum rows required for flush
    pub min_rows: i64,
    /// Maximum WAL size in bytes before flush
    pub max_bytes: i64,
    /// Minimum bytes before warm snapshot
    pub warm_snapshot_bytes: i64,
}

/// gRPC server configuration.
#[derive(Clone, Debug)]
pub struct ServerConfig {
    /// Public port for OTLP ingestion (authenticated)
    pub public_port: u16,
    /// Internal port for WAL reader service
    pub internal_port: u16,
}

/// Backend service connection configuration.
#[derive(Clone, Debug)]
pub struct BackendConfig {
    /// Backend gRPC host
    pub host: String,
    /// Backend gRPC port
    pub port: u16,
}

/// Authentication configuration.
#[derive(Clone, Debug)]
pub struct AuthConfig {
    /// TTL for API key cache entries
    pub cache_ttl: Duration,
    /// Maximum cache size
    pub cache_max_size: u64,
}

/// Logging configuration.
#[derive(Clone, Debug)]
pub struct LogConfig {
    /// Log level (trace, debug, info, warn, error)
    pub level: String,
    /// Log format (json, text)
    pub format: String,
}

impl Default for Config {
    fn default() -> Self {
        let home_dir = dirs_home().unwrap_or_else(|| PathBuf::from("."));

        Self {
            storage: StorageConfig {
                wal_path: home_dir.join(".junjo").join("ingestion-wal").join("fjall"),
            },
            flusher: FlusherConfig {
                output_dir: home_dir.join(".junjo").join("spans"),
                interval: Duration::from_secs(15),
                max_age: Duration::from_secs(3600), // 1 hour
                max_rows: 100_000,
                min_rows: 1_000,
                max_bytes: 50 * 1024 * 1024,       // 50MB
                warm_snapshot_bytes: 10 * 1024 * 1024, // 10MB
            },
            server: ServerConfig {
                public_port: 50051,
                internal_port: 50052,
            },
            backend: BackendConfig {
                host: "junjo-ai-studio-backend".to_string(),
                port: 50053,
            },
            auth: AuthConfig {
                cache_ttl: Duration::from_secs(300), // 5 minutes
                cache_max_size: 10_000,
            },
            log: LogConfig {
                level: "info".to_string(),
                format: "json".to_string(),
            },
        }
    }
}

impl Config {
    /// Load configuration from environment variables.
    pub fn from_env() -> Self {
        let mut config = Self::default();

        // Storage configuration
        if let Ok(path) = env::var("JUNJO_WAL_PATH") {
            config.storage.wal_path = PathBuf::from(path);
        }

        // Flusher configuration
        if let Ok(path) = env::var("PARQUET_STORAGE_PATH") {
            config.flusher.output_dir = PathBuf::from(path);
        }
        if let Ok(val) = env::var("FLUSH_INTERVAL") {
            if let Ok(secs) = parse_duration(&val) {
                config.flusher.interval = secs;
            }
        }
        if let Ok(val) = env::var("FLUSH_MAX_AGE") {
            if let Ok(secs) = parse_duration(&val) {
                config.flusher.max_age = secs;
            }
        }
        if let Ok(val) = env::var("FLUSH_MAX_ROWS") {
            if let Ok(n) = val.parse() {
                config.flusher.max_rows = n;
            }
        }
        if let Ok(val) = env::var("FLUSH_MIN_ROWS") {
            if let Ok(n) = val.parse() {
                config.flusher.min_rows = n;
            }
        }
        if let Ok(val) = env::var("FLUSH_MAX_BYTES") {
            if let Ok(n) = val.parse() {
                config.flusher.max_bytes = n;
            }
        }
        if let Ok(val) = env::var("WARM_SNAPSHOT_BYTES") {
            if let Ok(n) = val.parse() {
                config.flusher.warm_snapshot_bytes = n;
            }
        }

        // Server configuration
        if let Ok(port) = env::var("GRPC_PORT") {
            if let Ok(p) = port.parse() {
                config.server.public_port = p;
            }
        }
        if let Ok(port) = env::var("INTERNAL_GRPC_PORT") {
            if let Ok(p) = port.parse() {
                config.server.internal_port = p;
            }
        }

        // Backend configuration
        if let Ok(host) = env::var("BACKEND_GRPC_HOST") {
            config.backend.host = host;
        }
        if let Ok(port) = env::var("BACKEND_GRPC_PORT") {
            if let Ok(p) = port.parse() {
                config.backend.port = p;
            }
        }

        // Auth configuration
        if let Ok(val) = env::var("API_KEY_CACHE_TTL") {
            if let Ok(secs) = parse_duration(&val) {
                config.auth.cache_ttl = secs;
            }
        }

        // Log configuration
        if let Ok(level) = env::var("JUNJO_LOG_LEVEL") {
            config.log.level = level;
        }
        if let Ok(format) = env::var("JUNJO_LOG_FORMAT") {
            config.log.format = format;
        }

        config
    }
}

/// Parse a duration string like "15s", "1h", "30m"
fn parse_duration(s: &str) -> Result<Duration, ()> {
    let s = s.trim();
    if s.is_empty() {
        return Err(());
    }

    let (num_str, unit) = if s.ends_with("ms") {
        (&s[..s.len() - 2], "ms")
    } else if s.ends_with('s') {
        (&s[..s.len() - 1], "s")
    } else if s.ends_with('m') {
        (&s[..s.len() - 1], "m")
    } else if s.ends_with('h') {
        (&s[..s.len() - 1], "h")
    } else {
        // Assume seconds if no unit
        (s, "s")
    };

    let num: u64 = num_str.parse().map_err(|_| ())?;

    Ok(match unit {
        "ms" => Duration::from_millis(num),
        "s" => Duration::from_secs(num),
        "m" => Duration::from_secs(num * 60),
        "h" => Duration::from_secs(num * 3600),
        _ => return Err(()),
    })
}

/// Get user home directory
fn dirs_home() -> Option<PathBuf> {
    env::var_os("HOME").map(PathBuf::from)
}
