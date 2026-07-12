use std::time::Duration;

use tonic::transport::Channel;
use tracing::{debug, warn};

use crate::proto::{
    internal_auth_service_client::InternalAuthServiceClient, ValidateApiKeyRequest,
};

/// Client for communicating with the backend service.
pub struct BackendClient {
    addr: String,
}

impl BackendClient {
    pub fn new(addr: String) -> Self {
        Self { addr }
    }

    /// Get a connected client with default timeout (for quick operations like API key validation).
    async fn get_client(&self) -> anyhow::Result<InternalAuthServiceClient<Channel>> {
        self.get_client_with_timeout(Duration::from_secs(10)).await
    }

    /// Get a connected client with custom timeout.
    async fn get_client_with_timeout(
        &self,
        timeout: Duration,
    ) -> anyhow::Result<InternalAuthServiceClient<Channel>> {
        let start = std::time::Instant::now();
        debug!(addr = %self.addr, "Creating new gRPC connection to backend");

        let channel = Channel::from_shared(self.addr.clone())?
            .connect_timeout(Duration::from_secs(5))
            .timeout(timeout)
            .connect()
            .await?;

        let duration = start.elapsed();
        if duration.as_millis() > 100 {
            warn!(addr = %self.addr, duration_ms = duration.as_millis(), "Slow backend connection");
        } else {
            debug!(addr = %self.addr, duration_ms = duration.as_millis(), "Backend connection established");
        }

        Ok(InternalAuthServiceClient::new(channel))
    }

    /// Validate an API key with the backend.
    pub async fn validate_api_key(&self, api_key: &str) -> anyhow::Result<bool> {
        let mut client = match self.get_client().await {
            Ok(c) => c,
            Err(e) => {
                warn!(error = %e, "Failed to connect to backend for API key validation");
                // If backend is unavailable, reject for safety
                return Ok(false);
            }
        };

        let request = ValidateApiKeyRequest {
            api_key: api_key.to_string(),
        };

        let response = client.validate_api_key(request).await?;
        let is_valid = response.into_inner().is_valid;

        debug!(is_valid = is_valid, "API key validation result");

        Ok(is_valid)
    }
}
