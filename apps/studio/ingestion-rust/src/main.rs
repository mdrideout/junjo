// Suppress warnings during development - remove these for production audits
#![allow(unused_variables)]

// Use mimalloc as the global allocator - returns memory to OS while being fast
#[cfg(not(target_env = "msvc"))]
#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

use std::net::SocketAddr;
use std::sync::Arc;

use tokio::sync::{mpsc, RwLock};
use tonic::transport::Server;
use tracing::info;
use tracing_subscriber::EnvFilter;

mod config;
mod wal;
mod server;
mod flusher;
mod backend;

pub mod proto {
    tonic::include_proto!("ingestion");
}

use config::Config;
use wal::ArrowWal;
use server::{TraceService, InternalService};
use flusher::Flusher;
use backend::BackendClient;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Load configuration
    let config = Config::from_env();

    // Initialize tracing
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(&config.log_level));

    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(true)
        .json()
        .init();

    info!(
        grpc_port = config.grpc_port,
        internal_port = config.internal_grpc_port,
        wal_dir = %config.wal_dir.display(),
        snapshot_path = %config.snapshot_path.display(),
        parquet_dir = %config.parquet_output_dir.display(),
        flush_max_mb = config.flush_max_bytes / 1024 / 1024,
        batch_size = config.batch_size,
        backpressure_max_mb = config.backpressure_max_bytes / 1024 / 1024,
        "Starting ingestion-rust service"
    );

    // Ensure directories exist
    std::fs::create_dir_all(&config.wal_dir)?;
    std::fs::create_dir_all(&config.parquet_output_dir)?;

    // Initialize shared WAL (segmented log)
    let wal = Arc::new(RwLock::new(ArrowWal::new(
        &config.wal_dir,
        config.batch_size,
    )?));

    // Initialize backend client
    let backend_client = Arc::new(BackendClient::new(config.backend_addr()));

    // Create channel for reactive flush notifications (TraceService -> Flusher)
    // Buffer of 16 allows burst of segment writes without blocking gRPC handlers
    let (segment_tx, segment_rx) = mpsc::channel::<()>(16);

    // Initialize flusher
    let flusher = Arc::new(Flusher::new(
        Arc::clone(&wal),
        config.parquet_output_dir.clone(),
        config.flush_max_bytes,
        config.flush_max_age_secs,
        Arc::clone(&backend_client),
    ));

    // Start flusher background task with the segment notification receiver
    let flusher_handle = flusher.clone();
    tokio::spawn(async move {
        flusher_handle.run(segment_rx).await;
    });

    // Create gRPC services
    let trace_service = TraceService::new(
        Arc::clone(&wal),
        Arc::clone(&backend_client),
        config.backpressure_max_bytes,
        segment_tx,
    );

    let internal_service = InternalService::new(
        Arc::clone(&wal),
        Arc::clone(&flusher),
        config.snapshot_path.clone(),
    );

    // Start servers concurrently
    let public_addr: SocketAddr = format!("0.0.0.0:{}", config.grpc_port).parse()?;
    let internal_addr: SocketAddr = format!("0.0.0.0:{}", config.internal_grpc_port).parse()?;

    info!(%public_addr, "Starting public gRPC server (OTLP)");
    info!(%internal_addr, "Starting internal gRPC server");

    // Run both servers
    tokio::try_join!(
        run_public_server(public_addr, trace_service),
        run_internal_server(internal_addr, internal_service),
    )?;

    Ok(())
}

async fn run_public_server(
    addr: SocketAddr,
    trace_service: TraceService,
) -> anyhow::Result<()> {
    use opentelemetry_proto::tonic::collector::trace::v1::trace_service_server::TraceServiceServer;

    Server::builder()
        .add_service(TraceServiceServer::new(trace_service))
        .serve(addr)
        .await?;

    Ok(())
}

async fn run_internal_server(
    addr: SocketAddr,
    internal_service: InternalService,
) -> anyhow::Result<()> {
    use proto::internal_ingestion_service_server::InternalIngestionServiceServer;

    Server::builder()
        .add_service(InternalIngestionServiceServer::new(internal_service))
        .serve(addr)
        .await?;

    Ok(())
}
