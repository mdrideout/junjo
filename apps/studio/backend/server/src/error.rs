//! The one HTTP error body.
//!
//! Every error response is `{"code": "...", "message": "..."}`. A few errors
//! carry further members beside those two, such as the scopes a token lacks.
//! Status 422 is reserved for caller validation (Studio ADR-007).

use axum::Json;
use axum::extract::rejection::JsonRejection;
use axum::extract::{FromRequest, FromRequestParts, Path, Query, Request};
use axum::http::header::WWW_AUTHENTICATE;
use axum::http::request::Parts;
use axum::http::{HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use serde::Serialize;
use serde::de::DeserializeOwned;
use utoipa::ToSchema;

use crate::db::DbError;

/// The body of every error response.
#[derive(Debug, Serialize, ToSchema)]
pub struct ErrorResponse {
    /// A stable machine-readable code.
    #[schema(examples("not_found"))]
    pub code: String,
    /// A human-readable explanation.
    pub message: String,
}

#[derive(Debug)]
pub struct ApiError {
    pub status: StatusCode,
    pub code: &'static str,
    pub message: String,
    /// Members that accompany `code` and `message` for this error.
    pub extra: serde_json::Map<String, serde_json::Value>,
    /// Tell the caller that a bearer credential is expected.
    pub bearer_challenge: bool,
}

impl ApiError {
    pub fn new(status: StatusCode, code: &'static str, message: impl Into<String>) -> Self {
        Self {
            status,
            code,
            message: message.into(),
            extra: serde_json::Map::new(),
            bearer_challenge: false,
        }
    }

    /// Add one member beside `code` and `message`.
    pub fn with_extra(mut self, name: &str, value: impl Into<serde_json::Value>) -> Self {
        self.extra.insert(name.to_string(), value.into());
        self
    }

    /// Answer with `WWW-Authenticate: Bearer`.
    pub fn with_bearer_challenge(mut self) -> Self {
        self.bearer_challenge = true;
        self
    }

    pub fn unauthorized(message: impl Into<String>) -> Self {
        Self::new(StatusCode::UNAUTHORIZED, "unauthorized", message)
    }

    pub fn not_found(message: impl Into<String>) -> Self {
        Self::new(StatusCode::NOT_FOUND, "not_found", message)
    }

    /// The request conflicts with stored state. `code` names the conflict.
    pub fn conflict(code: &'static str, message: impl Into<String>) -> Self {
        Self::new(StatusCode::CONFLICT, code, message)
    }

    /// The caller sent a request Studio cannot interpret.
    pub fn validation(message: impl Into<String>) -> Self {
        Self::new(StatusCode::UNPROCESSABLE_ENTITY, "invalid_request", message)
    }

    pub fn internal() -> Self {
        Self::new(
            StatusCode::INTERNAL_SERVER_ERROR,
            "internal_error",
            "Internal server error",
        )
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let mut body = serde_json::Map::new();
        body.insert("code".to_string(), self.code.into());
        body.insert("message".to_string(), self.message.into());
        body.extend(self.extra);
        let mut response = (self.status, Json(body)).into_response();
        if self.bearer_challenge {
            response
                .headers_mut()
                .insert(WWW_AUTHENTICATE, HeaderValue::from_static("Bearer"));
        }
        response
    }
}

impl From<DbError> for ApiError {
    fn from(error: DbError) -> Self {
        tracing::error!(error = %error, "database operation failed");
        Self::internal()
    }
}

/// A JSON request body. Any failure to read or interpret it is a caller
/// validation error with the standard error body.
pub struct ApiJson<T>(pub T);

impl<S, T> FromRequest<S> for ApiJson<T>
where
    S: Send + Sync,
    T: DeserializeOwned,
{
    type Rejection = ApiError;

    async fn from_request(request: Request, state: &S) -> Result<Self, Self::Rejection> {
        match Json::<T>::from_request(request, state).await {
            Ok(Json(value)) => Ok(Self(value)),
            Err(JsonRejection::BytesRejection(rejection))
                if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE =>
            {
                Err(ApiError::new(
                    StatusCode::PAYLOAD_TOO_LARGE,
                    "payload_too_large",
                    "Request body is too large",
                ))
            }
            // A body that is JSON but not the expected request: say which
            // member is wrong and why, without the parser's position in the
            // text. A user reads this message under a form.
            Err(JsonRejection::JsonDataError(rejection)) => {
                let reason = std::error::Error::source(&rejection)
                    .map(ToString::to_string)
                    .unwrap_or_else(|| rejection.body_text());
                let reason = match reason.rsplit_once(" at line ") {
                    Some((reason, _position)) => reason.to_string(),
                    None => reason,
                };
                Err(ApiError::validation(reason))
            }
            Err(rejection) => Err(ApiError::validation(rejection.body_text())),
        }
    }
}

/// Query parameters. A parameter Studio cannot interpret is a caller
/// validation error with the standard error body.
pub struct ApiQuery<T>(pub T);

impl<S, T> FromRequestParts<S> for ApiQuery<T>
where
    S: Send + Sync,
    T: DeserializeOwned,
{
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        match Query::<T>::from_request_parts(parts, state).await {
            Ok(Query(value)) => Ok(Self(value)),
            Err(rejection) => Err(ApiError::validation(rejection.body_text())),
        }
    }
}

/// Path parameters. A value Studio cannot interpret is a caller validation
/// error with the standard error body.
pub struct ApiPath<T>(pub T);

impl<S, T> FromRequestParts<S> for ApiPath<T>
where
    S: Send + Sync,
    T: DeserializeOwned + Send,
{
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        match Path::<T>::from_request_parts(parts, state).await {
            Ok(Path(value)) => Ok(Self(value)),
            // The route and the handler disagree about its parameters.
            Err(rejection) if rejection.status().is_server_error() => {
                tracing::error!(error = %rejection, "path parameters could not be read");
                Err(ApiError::internal())
            }
            Err(rejection) => Err(ApiError::validation(rejection.body_text())),
        }
    }
}

#[cfg(test)]
mod tests {
    use axum::body::to_bytes;
    use serde_json::{Value, json};

    use super::*;

    async fn rendered(error: ApiError) -> (StatusCode, Option<String>, Value) {
        let response = error.into_response();
        let status = response.status();
        let challenge = response
            .headers()
            .get(WWW_AUTHENTICATE)
            .map(|value| value.to_str().unwrap().to_string());
        let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        (status, challenge, serde_json::from_slice(&bytes).unwrap())
    }

    #[tokio::test]
    async fn every_error_has_a_code_and_a_message() {
        let (status, challenge, body) = rendered(ApiError::not_found("No such thing")).await;
        assert_eq!(status, StatusCode::NOT_FOUND);
        assert_eq!(challenge, None);
        assert_eq!(
            body,
            json!({"code": "not_found", "message": "No such thing"})
        );
    }

    #[tokio::test]
    async fn extra_members_sit_beside_the_code_and_message() {
        let error = ApiError::new(StatusCode::FORBIDDEN, "insufficient_scope", "Scope missing")
            .with_extra("missing_scopes", json!(["evidence:read"]))
            .with_bearer_challenge();
        let (status, challenge, body) = rendered(error).await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(challenge.as_deref(), Some("Bearer"));
        assert_eq!(
            body,
            json!({
                "code": "insufficient_scope",
                "message": "Scope missing",
                "missing_scopes": ["evidence:read"],
            })
        );
    }
}
