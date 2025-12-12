mod config;
mod proto;
mod server;
mod storage;
mod backend_client;

use std::sync::Arc;
use tokio::signal;
use tracing::{error, info};

use crate::config::Config;
use crate::server::Server;
use crate::storage::Repository;
use crate::backend_client::BackendClient;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Load configuration
    let config = Config::from_env();

    // Initialize logging
    init_logging(&config);

    info!(
        version = env!("CARGO_PKG_VERSION"),
        "Starting Junjo ingestion service (Rust)"
    );

    // Initialize storage
    let repository = Arc::new(Repository::new(&config.storage)?);
    info!(path = %config.storage.wal_path.display(), "Initialized fjall storage");

    // Initialize backend client for auth validation
    let backend_client = Arc::new(
        BackendClient::new(
            &config.backend.host,
            config.backend.port,
            config.auth.cache_ttl,
        )
        .await?,
    );
    info!(
        host = %config.backend.host,
        port = config.backend.port,
        "Connected to backend service"
    );

    // Create and start server
    let server = Server::new(config.clone(), repository.clone(), backend_client.clone());

    // Spawn server in background
    let server_handle = tokio::spawn(async move {
        if let Err(e) = server.run().await {
            error!(error = %e, "Server error");
        }
    });

    // Wait for shutdown signal
    shutdown_signal().await;
    info!("Shutdown signal received");

    // Graceful shutdown
    server_handle.abort();

    // Flush any remaining data
    if let Err(e) = repository.flush() {
        error!(error = %e, "Error during final flush");
    }

    info!("Shutdown complete");
    Ok(())
}

fn init_logging(config: &Config) {
    use tracing_subscriber::{fmt, prelude::*, EnvFilter};

    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(&config.log.level));

    let subscriber = tracing_subscriber::registry().with(filter);

    if config.log.format == "json" {
        subscriber
            .with(fmt::layer().json().flatten_event(true))
            .init();
    } else {
        subscriber.with(fmt::layer()).init();
    }
}

async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}
