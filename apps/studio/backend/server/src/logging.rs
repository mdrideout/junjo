//! Structured logging through `tracing`, following the ingestion service.

use tracing_subscriber::EnvFilter;

use crate::config::{Config, LogFormat};

pub fn init(config: &Config) {
    // RUST_LOG, when set, overrides the configured level for diagnosis.
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(config.log_level.as_str()));
    let builder = tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(true);
    match config.log_format {
        LogFormat::Json => builder.json().init(),
        LogFormat::Text => builder.init(),
    }
}
