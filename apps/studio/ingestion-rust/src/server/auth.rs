use std::sync::Arc;

use tonic::{Request, Status};
use tracing::{debug, warn};

use crate::backend_client::BackendClient;

/// Header name for the API key.
const API_KEY_HEADER: &str = "x-junjo-api-key";

/// AuthInterceptor validates API keys on incoming requests.
#[derive(Clone)]
pub struct AuthInterceptor {
    backend_client: Arc<BackendClient>,
}

impl AuthInterceptor {
    pub fn new(backend_client: Arc<BackendClient>) -> Self {
        Self { backend_client }
    }

    /// Intercept and validate the request.
    pub fn intercept<T>(&self, request: Request<T>) -> Result<Request<T>, Status> {
        // Extract API key from metadata
        let api_key = request
            .metadata()
            .get(API_KEY_HEADER)
            .and_then(|v| v.to_str().ok());

        match api_key {
            Some(key) if !key.is_empty() => {
                // Validate synchronously by blocking on the async call
                // This is acceptable because tonic interceptors are sync
                let backend = self.backend_client.clone();
                let key_owned = key.to_string();

                // We need to validate in a blocking context
                // Using tokio::task::block_in_place for this
                let is_valid = tokio::task::block_in_place(|| {
                    tokio::runtime::Handle::current().block_on(async {
                        backend.validate_api_key(&key_owned).await
                    })
                });

                match is_valid {
                    Ok(true) => {
                        debug!("API key validated successfully");
                        Ok(request)
                    }
                    Ok(false) => {
                        warn!("Invalid API key provided");
                        Err(Status::unauthenticated("Invalid API key"))
                    }
                    Err(e) => {
                        warn!(error = %e, "Failed to validate API key");
                        Err(Status::internal("Authentication service unavailable"))
                    }
                }
            }
            _ => {
                warn!("No API key provided");
                Err(Status::unauthenticated("API key required"))
            }
        }
    }
}
