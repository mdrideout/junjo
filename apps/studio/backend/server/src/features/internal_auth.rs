//! Internal gRPC service that ingestion calls to validate API keys.
//!
//! Studio ADR-009 governs the caller's caching and bounds. This side answers
//! one authoritative question: does this key exist?

use subtle::ConstantTimeEq;
use tonic::{Request, Response, Status};

use crate::db::Db;
use crate::features::api_keys::repo;
use crate::proto::internal_auth_service_server::InternalAuthService;
use crate::proto::{ValidateApiKeyRequest, ValidateApiKeyResponse};

const INTERNAL_TOKEN_HEADER: &str = "x-junjo-internal-token";

pub struct InternalAuth {
    reader: Db,
    internal_token: String,
}

impl InternalAuth {
    pub fn new(reader: Db, internal_token: String) -> Self {
        Self {
            reader,
            internal_token,
        }
    }

    fn has_valid_internal_token<T>(&self, request: &Request<T>) -> bool {
        let supplied = request
            .metadata()
            .get(INTERNAL_TOKEN_HEADER)
            .map(|value| value.as_bytes())
            .unwrap_or_default();
        supplied.ct_eq(self.internal_token.as_bytes()).into()
    }
}

#[tonic::async_trait]
impl InternalAuthService for InternalAuth {
    async fn validate_api_key(
        &self,
        request: Request<ValidateApiKeyRequest>,
    ) -> Result<Response<ValidateApiKeyResponse>, Status> {
        if !self.has_valid_internal_token(&request) {
            return Err(Status::unauthenticated("Invalid internal workload token"));
        }
        let api_key = request.into_inner().api_key;
        match self
            .reader
            .call(move |connection| repo::key_exists(connection, &api_key))
            .await
        {
            Ok(is_valid) => Ok(Response::new(ValidateApiKeyResponse { is_valid })),
            Err(error) => {
                tracing::error!(%error, "database error during API key validation");
                // Retryable: availability is not an authorization answer.
                Err(Status::unavailable("API key store unavailable"))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use tokio::net::TcpListener;
    use tonic::Code;
    use tonic::transport::Server;
    use tonic::transport::server::TcpIncoming;

    use super::*;
    use crate::features::api_keys::repo::ApiKey;
    use crate::proto::internal_auth_service_client::InternalAuthServiceClient;
    use crate::proto::internal_auth_service_server::InternalAuthServiceServer;
    use crate::test_support::{INTERNAL_TOKEN, test_app};
    use crate::timestamps::UtcSeconds;

    const KEY: &str = "jtel_test";

    async fn service_with_key() -> (InternalAuth, crate::test_support::TestApp) {
        let app = test_app();
        app.state
            .application_db
            .writer
            .call(|connection| {
                repo::create(
                    connection,
                    &ApiKey {
                        id: "key-1".to_string(),
                        key: KEY.to_string(),
                        name: "test".to_string(),
                        created_at: UtcSeconds::now(),
                    },
                )
            })
            .await
            .unwrap();
        let service = InternalAuth::new(
            app.state.application_db.reader.clone(),
            INTERNAL_TOKEN.to_string(),
        );
        (service, app)
    }

    fn request(api_key: &str, token: Option<&str>) -> Request<ValidateApiKeyRequest> {
        let mut request = Request::new(ValidateApiKeyRequest {
            api_key: api_key.to_string(),
        });
        if let Some(token) = token {
            request
                .metadata_mut()
                .insert(INTERNAL_TOKEN_HEADER, token.parse().unwrap());
        }
        request
    }

    #[tokio::test]
    async fn an_existing_key_is_valid_and_an_unknown_key_is_not() {
        let (service, _app) = service_with_key().await;

        let valid = service
            .validate_api_key(request(KEY, Some(INTERNAL_TOKEN)))
            .await
            .unwrap();
        assert!(valid.into_inner().is_valid);

        let unknown = service
            .validate_api_key(request("jtel_unknown", Some(INTERNAL_TOKEN)))
            .await
            .unwrap();
        assert!(!unknown.into_inner().is_valid);
    }

    #[tokio::test]
    async fn an_empty_key_is_an_authoritative_miss() {
        let (service, _app) = service_with_key().await;
        let empty = service
            .validate_api_key(request("", Some(INTERNAL_TOKEN)))
            .await
            .unwrap();
        assert!(!empty.into_inner().is_valid);
    }

    #[tokio::test]
    async fn a_store_failure_is_unavailable_not_an_invalid_key() {
        let (service, app) = service_with_key().await;
        let rename = |statement: &'static str| {
            let writer = app.state.application_db.writer.clone();
            async move {
                writer
                    .call(move |connection| connection.execute_batch(statement))
                    .await
                    .unwrap();
            }
        };

        rename("ALTER TABLE api_keys RENAME TO api_keys_away").await;
        let status = service
            .validate_api_key(request(KEY, Some(INTERNAL_TOKEN)))
            .await
            .unwrap_err();
        // Retryable: ingestion must not cache this as a rejection.
        assert_eq!(status.code(), Code::Unavailable);
        assert_eq!(status.message(), "API key store unavailable");

        rename("ALTER TABLE api_keys_away RENAME TO api_keys").await;
        let valid = service
            .validate_api_key(request(KEY, Some(INTERNAL_TOKEN)))
            .await
            .unwrap();
        assert!(valid.into_inner().is_valid);
    }

    #[tokio::test]
    async fn concurrent_validations_each_get_their_own_answer() {
        let (service, _app) = service_with_key().await;
        let service = std::sync::Arc::new(service);
        let mut tasks = tokio::task::JoinSet::new();
        for number in 0..100 {
            let service = service.clone();
            tasks.spawn(async move {
                let is_known = number % 2 == 0;
                let key = if is_known { KEY } else { "jtel_unknown" };
                let response = service
                    .validate_api_key(request(key, Some(INTERNAL_TOKEN)))
                    .await
                    .unwrap();
                (is_known, response.into_inner().is_valid)
            });
        }
        let mut answers = 0;
        while let Some(answer) = tasks.join_next().await {
            let (is_known, is_valid) = answer.unwrap();
            assert_eq!(is_valid, is_known);
            answers += 1;
        }
        assert_eq!(answers, 100);
    }

    #[tokio::test]
    async fn a_missing_or_wrong_internal_token_is_unauthenticated() {
        let (service, _app) = service_with_key().await;

        for token in [None, Some("wrong-token"), Some("")] {
            let status = service
                .validate_api_key(request(KEY, token))
                .await
                .unwrap_err();
            assert_eq!(status.code(), Code::Unauthenticated);
            assert_eq!(status.message(), "Invalid internal workload token");
        }
    }

    #[tokio::test]
    async fn the_service_answers_over_the_real_transport() {
        let (service, _app) = service_with_key().await;
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(
            Server::builder()
                .add_service(InternalAuthServiceServer::new(service))
                .serve_with_incoming(TcpIncoming::from(listener)),
        );

        let mut client = InternalAuthServiceClient::connect(format!("http://{address}"))
            .await
            .unwrap();
        let valid = client
            .validate_api_key(request(KEY, Some(INTERNAL_TOKEN)))
            .await
            .unwrap();
        assert!(valid.into_inner().is_valid);
        let rejected = client
            .validate_api_key(request(KEY, None))
            .await
            .unwrap_err();
        assert_eq!(rejected.code(), Code::Unauthenticated);

        server.abort();
    }
}
