use std::sync::Arc;
use std::time::Duration;

use moka::future::Cache;
use tonic::{Request, Status};
use tracing::{debug, warn};

use crate::backend::BackendClient;

/// Interceptor for API key authentication with caching.
/// Uses moka cache (similar to Go's otter) with:
/// - 10,000 key capacity
/// - 10 minute TTL for valid keys
/// - Invalid keys are NOT cached (matches Go behavior)
pub struct ApiKeyInterceptor {
    backend: Arc<BackendClient>,
    /// Cache of validated API keys (only valid keys are cached)
    cache: Cache<String, ()>,
}

impl ApiKeyInterceptor {
    pub fn new(backend: Arc<BackendClient>) -> Self {
        let cache = Cache::builder()
            .max_capacity(10_000)
            .time_to_live(Duration::from_secs(600)) // 10 minutes, matches Go
            .build();

        Self { backend, cache }
    }

    /// Validate an API key, using cache if available.
    pub async fn validate(&self, api_key: &str) -> Result<bool, Status> {
        // Check cache first - only valid keys are cached
        if self.cache.contains_key(api_key) {
            return Ok(true);
        }

        // Cache miss - validate with backend
        debug!("API key cache miss, calling backend");
        let start = std::time::Instant::now();

        let is_valid = self
            .backend
            .validate_api_key(api_key)
            .await
            .map_err(|e| {
                warn!(error = %e, duration_ms = start.elapsed().as_millis(), "Failed to validate API key with backend");
                Status::internal("Failed to validate API key")
            })?;

        let duration = start.elapsed();
        if duration.as_millis() > 5000 {
            warn!(
                duration_ms = duration.as_millis(),
                is_valid = is_valid,
                "Slow backend API key validation"
            );
        }

        // Only cache valid keys (invalid keys always hit backend)
        // This allows newly activated keys to work immediately
        if is_valid {
            self.cache.insert(api_key.to_string(), ()).await;
            debug!("API key cached after successful validation");
        }

        Ok(is_valid)
    }

    /// Extract API key from request metadata.
    pub fn extract_api_key<T>(request: &Request<T>) -> Option<String> {
        request
            .metadata()
            .get("x-junjo-api-key")
            .and_then(|v| v.to_str().ok())
            .map(|s| s.to_string())
    }
}
