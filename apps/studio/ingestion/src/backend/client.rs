use std::time::Duration;

use tonic::transport::Channel;
use tracing::debug;

use crate::proto::{
    internal_auth_service_client::InternalAuthServiceClient, ValidateApiKeyRequest,
};

/// Client for communicating with the backend service.
pub struct BackendClient {
    addr: String,
    internal_grpc_token: String,
    channel: Channel,
}

impl BackendClient {
    /// Create one lazy, reconnecting HTTP/2 channel shared by every validation.
    pub fn new(
        addr: String,
        internal_grpc_token: String,
        request_timeout: Duration,
    ) -> anyhow::Result<Self> {
        let channel = Channel::from_shared(addr.clone())?
            .connect_timeout(request_timeout)
            .timeout(request_timeout)
            .connect_lazy();

        Ok(Self {
            addr,
            internal_grpc_token,
            channel,
        })
    }

    /// Validate an API key with the backend.
    pub async fn validate_api_key(&self, api_key: &str) -> anyhow::Result<bool> {
        // Tonic Channel clones share one multiplexed connection and reconnect
        // automatically after the backend becomes reachable again.
        let mut client = InternalAuthServiceClient::new(self.channel.clone());

        let mut request = tonic::Request::new(ValidateApiKeyRequest {
            api_key: api_key.to_string(),
        });
        request
            .metadata_mut()
            .insert("x-junjo-internal-token", self.internal_grpc_token.parse()?);

        let response = client.validate_api_key(request).await?;
        let is_valid = response.into_inner().is_valid;

        debug!(addr = %self.addr, is_valid, "API key validation result");

        Ok(is_valid)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::SocketAddr;

    use tokio::net::TcpListener;
    use tokio::sync::oneshot;
    use tokio_stream::wrappers::TcpListenerStream;
    use tonic::{Response, Status};

    use crate::proto::{
        internal_auth_service_server::{InternalAuthService, InternalAuthServiceServer},
        ValidateApiKeyResponse,
    };

    const INTERNAL_TOKEN: &str = "test-internal-grpc-token-32-bytes-long";

    #[derive(Default)]
    struct TestAuthService;

    #[tonic::async_trait]
    impl InternalAuthService for TestAuthService {
        async fn validate_api_key(
            &self,
            request: tonic::Request<ValidateApiKeyRequest>,
        ) -> Result<Response<ValidateApiKeyResponse>, Status> {
            let supplied_token = request
                .metadata()
                .get("x-junjo-internal-token")
                .and_then(|value| value.to_str().ok());
            if supplied_token != Some(INTERNAL_TOKEN) {
                return Err(Status::unauthenticated("invalid workload token"));
            }
            Ok(Response::new(ValidateApiKeyResponse {
                is_valid: request.into_inner().api_key == "valid-key",
            }))
        }
    }

    async fn start_server(
        addr: Option<SocketAddr>,
    ) -> (
        SocketAddr,
        oneshot::Sender<()>,
        tokio::task::JoinHandle<Result<(), tonic::transport::Error>>,
    ) {
        let listener = TcpListener::bind(addr.unwrap_or_else(|| "127.0.0.1:0".parse().unwrap()))
            .await
            .unwrap();
        let addr = listener.local_addr().unwrap();
        let (shutdown_tx, shutdown_rx) = oneshot::channel();
        let handle = tokio::spawn(async move {
            tonic::transport::Server::builder()
                .add_service(InternalAuthServiceServer::new(TestAuthService))
                .serve_with_incoming_shutdown(TcpListenerStream::new(listener), async {
                    let _ = shutdown_rx.await;
                })
                .await
        });
        (addr, shutdown_tx, handle)
    }

    #[tokio::test]
    async fn shared_channel_reconnects_after_backend_restart() {
        let (addr, shutdown, server) = start_server(None).await;
        let client = BackendClient::new(
            format!("http://{addr}"),
            INTERNAL_TOKEN.to_string(),
            Duration::from_millis(250),
        )
        .unwrap();

        assert!(client.validate_api_key("valid-key").await.unwrap());
        assert!(!client.validate_api_key("invalid-key").await.unwrap());

        shutdown.send(()).unwrap();
        server.await.unwrap().unwrap();
        assert!(client.validate_api_key("valid-key").await.is_err());

        let (_addr, restart_shutdown, restarted_server) = start_server(Some(addr)).await;
        let mut reconnected = false;
        for _ in 0..30 {
            if matches!(client.validate_api_key("valid-key").await, Ok(true)) {
                reconnected = true;
                break;
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        assert!(reconnected, "the existing channel did not reconnect");

        restart_shutdown.send(()).unwrap();
        restarted_server.await.unwrap().unwrap();
    }
}
