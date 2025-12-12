mod auth;
mod trace_service;
mod internal_service;

use std::net::SocketAddr;
use std::sync::Arc;

use anyhow::{Context, Result};
use tonic::transport::Server as TonicServer;
use tonic_health::server::health_reporter;
use tracing::info;

use crate::backend_client::BackendClient;
use crate::config::Config;
use crate::proto::{InternalIngestionServiceServer, TraceServiceServer};
use crate::storage::Repository;

pub use auth::AuthInterceptor;
pub use trace_service::OtlpTraceService;
pub use internal_service::InternalIngestionServiceImpl;

/// Server manages both public and internal gRPC servers.
pub struct Server {
    config: Config,
    repository: Arc<Repository>,
    backend_client: Arc<BackendClient>,
}

impl Server {
    pub fn new(
        config: Config,
        repository: Arc<Repository>,
        backend_client: Arc<BackendClient>,
    ) -> Self {
        Self {
            config,
            repository,
            backend_client,
        }
    }

    /// Run both public and internal gRPC servers.
    pub async fn run(&self) -> Result<()> {
        let public_handle = self.run_public_server();
        let internal_handle = self.run_internal_server();

        // Run both servers concurrently
        tokio::try_join!(public_handle, internal_handle)?;

        Ok(())
    }

    /// Run the public gRPC server (OTLP ingestion with authentication).
    async fn run_public_server(&self) -> Result<()> {
        let addr: SocketAddr = format!("0.0.0.0:{}", self.config.server.public_port)
            .parse()
            .context("Invalid public server address")?;

        // Create trace service
        let trace_service = OtlpTraceService::new(self.repository.clone());

        // Create auth interceptor
        let auth_interceptor = AuthInterceptor::new(self.backend_client.clone());

        // Set up health reporter
        let (mut health_reporter, health_service) = health_reporter();
        health_reporter
            .set_serving::<TraceServiceServer<OtlpTraceService>>()
            .await;

        info!(addr = %addr, "Starting public gRPC server (OTLP)");

        TonicServer::builder()
            .add_service(health_service)
            .add_service(TraceServiceServer::with_interceptor(
                trace_service,
                move |req| auth_interceptor.clone().intercept(req),
            ))
            .serve(addr)
            .await
            .context("Public gRPC server failed")?;

        Ok(())
    }

    /// Run the internal gRPC server (WAL reader, no authentication).
    async fn run_internal_server(&self) -> Result<()> {
        let addr: SocketAddr = format!("0.0.0.0:{}", self.config.server.internal_port)
            .parse()
            .context("Invalid internal server address")?;

        // Create internal service
        let internal_service = InternalIngestionServiceImpl::new(
            self.repository.clone(),
            self.backend_client.clone(),
        );

        // Set up health reporter
        let (mut health_reporter, health_service) = health_reporter();
        health_reporter
            .set_serving::<InternalIngestionServiceServer<InternalIngestionServiceImpl>>()
            .await;

        info!(addr = %addr, "Starting internal gRPC server");

        TonicServer::builder()
            .add_service(health_service)
            .add_service(InternalIngestionServiceServer::new(internal_service))
            .serve(addr)
            .await
            .context("Internal gRPC server failed")?;

        Ok(())
    }
}
