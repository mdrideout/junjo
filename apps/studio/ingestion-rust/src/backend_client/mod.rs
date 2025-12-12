use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use moka::future::Cache;
use tonic::transport::Channel;
use tracing::{debug, warn};

use crate::proto::ingestion::internal_auth_service_client::InternalAuthServiceClient;
use crate::proto::ingestion::{
    NotifyNewParquetFileRequest, ValidateApiKeyRequest,
};

/// BackendClient handles communication with the Python backend service.
/// Provides API key validation with caching and Parquet file notifications.
pub struct BackendClient {
    client: InternalAuthServiceClient<Channel>,
    cache: Cache<String, bool>,
}

impl BackendClient {
    /// Create a new backend client.
    pub async fn new(host: &str, port: u16, cache_ttl: Duration) -> Result<Self> {
        let addr = format!("http://{}:{}", host, port);

        let channel = Channel::from_shared(addr.clone())
            .context("Invalid backend address")?
            .connect_timeout(Duration::from_secs(10))
            .timeout(Duration::from_secs(30))
            .connect()
            .await
            .with_context(|| format!("Failed to connect to backend at {}", addr))?;

        let client = InternalAuthServiceClient::new(channel);

        // Build cache with TTL
        let cache = Cache::builder()
            .time_to_live(cache_ttl)
            .max_capacity(10_000)
            .build();

        Ok(Self { client, cache })
    }

    /// Validate an API key. Returns true if valid, false otherwise.
    /// Results are cached to reduce backend load.
    pub async fn validate_api_key(&self, api_key: &str) -> Result<bool> {
        // Check cache first
        if let Some(valid) = self.cache.get(api_key).await {
            debug!(cached = true, "API key validation result");
            return Ok(valid);
        }

        // Call backend
        let request = tonic::Request::new(ValidateApiKeyRequest {
            api_key: api_key.to_string(),
        });

        let response = self
            .client
            .clone()
            .validate_api_key(request)
            .await
            .context("Failed to validate API key")?;

        let is_valid = response.into_inner().is_valid;

        // Cache the result
        self.cache.insert(api_key.to_string(), is_valid).await;
        debug!(cached = false, is_valid, "API key validation result");

        Ok(is_valid)
    }

    /// Notify backend of a newly created Parquet file for indexing.
    pub async fn notify_new_parquet_file(&self, file_path: &str) -> Result<(bool, i64)> {
        let request = tonic::Request::new(NotifyNewParquetFileRequest {
            file_path: file_path.to_string(),
        });

        let response = self
            .client
            .clone()
            .notify_new_parquet_file(request)
            .await
            .with_context(|| format!("Failed to notify backend of file: {}", file_path))?;

        let inner = response.into_inner();
        Ok((inner.indexed, inner.span_count))
    }
}
