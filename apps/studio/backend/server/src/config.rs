//! Process configuration.
//!
//! Configuration is read once from the process environment and validated
//! before anything else starts. A missing or invalid value stops the process
//! with a message that names the variable.

use std::fmt::Display;
use std::path::PathBuf;
use std::str::FromStr;
use std::time::Duration;

/// The OTLP endpoint of a local development stack.
const DEV_OTLP_ENDPOINT: &str = "grpc://localhost:26155";

/// Running environment. Production turns on `Secure` session cookies and
/// requires the public ingestion URL.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Environment {
    Development,
    Production,
}

impl Environment {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Development => "development",
            Self::Production => "production",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LogFormat {
    Json,
    Text,
}

/// DataFusion runtime settings for memory-constrained hosts.
#[derive(Debug, Clone)]
pub struct DataFusionConfig {
    pub target_partitions: usize,
    pub batch_size: usize,
    pub parquet_pruning: bool,
    pub spill_enabled: bool,
    pub spill_pool_bytes: usize,
    pub spill_path: PathBuf,
}

#[derive(Debug, Clone)]
pub struct Config {
    pub environment: Environment,
    pub http_port: u16,
    pub grpc_port: u16,
    pub internal_grpc_token: String,
    /// The public OTLP endpoint of a production deployment.
    pub prod_ingestion_url: Option<String>,
    pub log_level: tracing::Level,
    pub log_format: LogFormat,
    pub sqlite_path: PathBuf,
    pub metadata_db_path: PathBuf,
    pub parquet_storage_path: PathBuf,
    /// The built UI to serve. The production image sets it; without it the
    /// process serves the API only.
    pub ui_dir: Option<PathBuf>,
    pub ingestion_host: String,
    pub ingestion_port: u16,
    pub indexer_poll_interval: Duration,
    pub indexer_batch_size: usize,
    pub datafusion: DataFusionConfig,
}

#[derive(Debug, thiserror::Error)]
#[error("{0}")]
pub struct ConfigError(String);

impl Config {
    /// Load configuration from the process environment.
    pub fn from_env() -> Result<Self, ConfigError> {
        Self::from_lookup(|name| std::env::var(name).ok())
    }

    /// Load configuration from any name-to-value lookup. Tests use this so
    /// they never mutate the process environment.
    pub fn from_lookup(lookup: impl Fn(&str) -> Option<String>) -> Result<Self, ConfigError> {
        // An empty value means "not set", as it does in a Compose `.env` file.
        let get = |name: &str| lookup(name).filter(|value| !value.trim().is_empty());

        let environment = match get("JUNJO_ENV").as_deref() {
            None | Some("development") => Environment::Development,
            Some("production") => Environment::Production,
            Some(other) => {
                return Err(ConfigError(format!(
                    "JUNJO_ENV must be development or production, got {other:?}"
                )));
            }
        };

        let internal_grpc_token = get("JUNJO_INTERNAL_GRPC_TOKEN")
            .ok_or_else(|| ConfigError("JUNJO_INTERNAL_GRPC_TOKEN is required".to_string()))?;
        if internal_grpc_token.len() < 32 {
            return Err(ConfigError(
                "JUNJO_INTERNAL_GRPC_TOKEN must be at least 32 characters".to_string(),
            ));
        }

        let prod_ingestion_url = get("JUNJO_PROD_INGESTION_URL");
        if let Some(url) = &prod_ingestion_url
            && !url.starts_with("http://")
            && !url.starts_with("https://")
        {
            return Err(ConfigError(format!(
                "JUNJO_PROD_INGESTION_URL must start with http:// or https://, got {url:?}"
            )));
        }
        if environment == Environment::Production && prod_ingestion_url.is_none() {
            return Err(ConfigError(
                "JUNJO_PROD_INGESTION_URL is required when JUNJO_ENV=production".to_string(),
            ));
        }

        let log_level = match get("JUNJO_LOG_LEVEL")
            .unwrap_or_else(|| "info".to_string())
            .to_ascii_lowercase()
            .as_str()
        {
            "trace" => tracing::Level::TRACE,
            "debug" => tracing::Level::DEBUG,
            "info" => tracing::Level::INFO,
            "warn" | "warning" => tracing::Level::WARN,
            "error" | "critical" => tracing::Level::ERROR,
            other => {
                return Err(ConfigError(format!(
                    "JUNJO_LOG_LEVEL must be debug, info, warn, or error, got {other:?}"
                )));
            }
        };
        let log_format = match get("JUNJO_LOG_FORMAT").as_deref() {
            Some(value) if value.eq_ignore_ascii_case("text") => LogFormat::Text,
            _ => LogFormat::Json,
        };

        Ok(Self {
            environment,
            http_port: ranged(&get, "PORT", 26154u16, 1, 65535)?,
            grpc_port: ranged(&get, "GRPC_PORT", 50053u16, 1, 65535)?,
            internal_grpc_token,
            prod_ingestion_url,
            log_level,
            log_format,
            sqlite_path: PathBuf::from(
                get("JUNJO_SQLITE_PATH").unwrap_or_else(|| "../.dbdata/sqlite/junjo.db".into()),
            ),
            metadata_db_path: PathBuf::from(
                get("JUNJO_METADATA_DB_PATH")
                    .unwrap_or_else(|| "../.dbdata/sqlite/metadata.db".into()),
            ),
            parquet_storage_path: PathBuf::from(
                get("JUNJO_PARQUET_STORAGE_PATH").unwrap_or_else(|| "../.dbdata/parquet".into()),
            ),
            ui_dir: get("JUNJO_UI_DIR").map(PathBuf::from),
            ingestion_host: get("INGESTION_HOST").unwrap_or_else(|| "ingestion".to_string()),
            ingestion_port: ranged(&get, "INGESTION_PORT", 50052u16, 1, 65535)?,
            indexer_poll_interval: Duration::from_secs(ranged(
                &get,
                "INDEXER_POLL_INTERVAL",
                30u64,
                5,
                3600,
            )?),
            indexer_batch_size: ranged(&get, "INDEXER_BATCH_SIZE", 10usize, 1, 100)?,
            datafusion: DataFusionConfig {
                target_partitions: ranged(&get, "JUNJO_DF_TARGET_PARTITIONS", 1usize, 1, 32)?,
                batch_size: ranged(&get, "JUNJO_DF_BATCH_SIZE", 4096usize, 512, 65536)?,
                parquet_pruning: boolean(&get, "JUNJO_DF_PARQUET_PRUNING", true)?,
                spill_enabled: boolean(&get, "JUNJO_DF_SPILL_ENABLED", true)?,
                spill_pool_bytes: ranged(&get, "JUNJO_DF_SPILL_POOL_MB", 192usize, 32, 4096)?
                    * 1024
                    * 1024,
                spill_path: PathBuf::from(
                    get("JUNJO_DF_SPILL_PATH")
                        .unwrap_or_else(|| "/tmp/junjo-datafusion-spill".into()),
                ),
            },
        })
    }

    pub fn is_production(&self) -> bool {
        self.environment == Environment::Production
    }

    /// Where SDKs send telemetry: the public ingestion URL when one is set,
    /// otherwise the development host port.
    pub fn otlp_endpoint(&self) -> String {
        self.prod_ingestion_url
            .clone()
            .unwrap_or_else(|| DEV_OTLP_ENDPOINT.to_string())
    }
}

fn ranged<T>(
    get: &impl Fn(&str) -> Option<String>,
    name: &str,
    default: T,
    min: T,
    max: T,
) -> Result<T, ConfigError>
where
    T: FromStr + PartialOrd + Display + Copy,
{
    let Some(raw) = get(name) else {
        return Ok(default);
    };
    let value: T = raw.trim().parse().map_err(|_| {
        ConfigError(format!(
            "{name} must be an integer between {min} and {max}, got {raw:?}"
        ))
    })?;
    if value < min || value > max {
        return Err(ConfigError(format!(
            "{name} must be between {min} and {max}, got {value}"
        )));
    }
    Ok(value)
}

fn boolean(
    get: &impl Fn(&str) -> Option<String>,
    name: &str,
    default: bool,
) -> Result<bool, ConfigError> {
    let Some(raw) = get(name) else {
        return Ok(default);
    };
    match raw.trim().to_ascii_lowercase().as_str() {
        "true" | "1" | "yes" | "on" => Ok(true),
        "false" | "0" | "no" | "off" => Ok(false),
        _ => Err(ConfigError(format!(
            "{name} must be true or false, got {raw:?}"
        ))),
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use super::*;

    const TOKEN: &str = "test-internal-grpc-token-32-bytes-long";

    fn load(values: &[(&str, &str)]) -> Result<Config, ConfigError> {
        let map: HashMap<String, String> = values
            .iter()
            .map(|(name, value)| (name.to_string(), value.to_string()))
            .collect();
        Config::from_lookup(|name| map.get(name).cloned())
    }

    #[test]
    fn defaults_match_the_documented_local_port_model() {
        let config = load(&[("JUNJO_INTERNAL_GRPC_TOKEN", TOKEN)]).unwrap();
        assert_eq!(config.environment, Environment::Development);
        assert_eq!(config.http_port, 26154);
        assert_eq!(config.grpc_port, 50053);
        assert_eq!(config.ingestion_host, "ingestion");
        assert_eq!(config.ingestion_port, 50052);
        assert_eq!(config.indexer_poll_interval, Duration::from_secs(30));
        assert_eq!(config.indexer_batch_size, 10);
        assert_eq!(config.datafusion.target_partitions, 1);
        assert_eq!(config.datafusion.batch_size, 4096);
        assert_eq!(config.datafusion.spill_pool_bytes, 192 * 1024 * 1024);
        assert!(config.datafusion.parquet_pruning);
        assert!(config.datafusion.spill_enabled);
        assert_eq!(config.log_format, LogFormat::Json);
        assert_eq!(config.log_level, tracing::Level::INFO);
    }

    #[test]
    fn the_internal_token_is_required_and_long() {
        assert!(load(&[]).unwrap_err().to_string().contains("is required"));
        let error = load(&[("JUNJO_INTERNAL_GRPC_TOKEN", "short")]).unwrap_err();
        assert!(error.to_string().contains("at least 32"));
    }

    #[test]
    fn production_requires_the_ingestion_url() {
        let error = load(&[
            ("JUNJO_INTERNAL_GRPC_TOKEN", TOKEN),
            ("JUNJO_ENV", "production"),
        ])
        .unwrap_err();
        assert!(error.to_string().contains("JUNJO_PROD_INGESTION_URL"));

        let config = load(&[
            ("JUNJO_INTERNAL_GRPC_TOKEN", TOKEN),
            ("JUNJO_ENV", "production"),
            ("JUNJO_PROD_INGESTION_URL", "https://ingestion.example.com"),
        ])
        .unwrap();
        assert!(config.is_production());
        assert_eq!(config.environment.as_str(), "production");
        // SDKs are told to send telemetry to the public ingestion URL.
        assert_eq!(config.otlp_endpoint(), "https://ingestion.example.com");
    }

    #[test]
    fn development_points_sdks_at_the_local_otlp_port() {
        let config = load(&[("JUNJO_INTERNAL_GRPC_TOKEN", TOKEN)]).unwrap();
        assert_eq!(config.environment.as_str(), "development");
        assert_eq!(config.otlp_endpoint(), "grpc://localhost:26155");
    }

    #[test]
    fn out_of_range_and_malformed_values_name_the_variable() {
        let error = load(&[
            ("JUNJO_INTERNAL_GRPC_TOKEN", TOKEN),
            ("INDEXER_POLL_INTERVAL", "2"),
        ])
        .unwrap_err();
        assert!(error.to_string().contains("INDEXER_POLL_INTERVAL"));

        let error = load(&[
            ("JUNJO_INTERNAL_GRPC_TOKEN", TOKEN),
            ("JUNJO_DF_BATCH_SIZE", "many"),
        ])
        .unwrap_err();
        assert!(error.to_string().contains("JUNJO_DF_BATCH_SIZE"));

        let error = load(&[
            ("JUNJO_INTERNAL_GRPC_TOKEN", TOKEN),
            ("JUNJO_ENV", "staging"),
        ])
        .unwrap_err();
        assert!(error.to_string().contains("JUNJO_ENV"));
    }

    #[test]
    fn python_style_log_levels_and_empty_values_are_accepted() {
        let config = load(&[
            ("JUNJO_INTERNAL_GRPC_TOKEN", TOKEN),
            ("JUNJO_LOG_LEVEL", "WARNING"),
            ("JUNJO_LOG_FORMAT", "text"),
            ("JUNJO_PROD_INGESTION_URL", ""),
        ])
        .unwrap();
        assert_eq!(config.log_level, tracing::Level::WARN);
        assert_eq!(config.log_format, LogFormat::Text);
        assert_eq!(config.prod_ingestion_url, None);
        // Without a UI directory the process serves the API only.
        assert_eq!(config.ui_dir, None);
        let with_ui = load(&[
            ("JUNJO_INTERNAL_GRPC_TOKEN", TOKEN),
            ("JUNJO_UI_DIR", "/usr/share/junjo/ui"),
        ])
        .unwrap();
        assert_eq!(with_ui.ui_dir, Some(PathBuf::from("/usr/share/junjo/ui")));
    }
}
