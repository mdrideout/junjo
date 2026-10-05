//! Helpers for tests that call the application through its router.

use axum::Router;
use axum::body::{Body, to_bytes};
use axum::http::header::{AUTHORIZATION, CONTENT_TYPE, COOKIE, SET_COOKIE};
use axum::http::{HeaderMap, Method, Request, StatusCode};
use serde_json::{Value, json};
use tower::ServiceExt;

use crate::app::router;
use crate::test_support::{TestApp, test_app};

pub const EMAIL: &str = "owner@example.com";
pub const PASSWORD: &str = "correct horse battery";

pub struct Reply {
    pub status: StatusCode,
    pub headers: HeaderMap,
    pub body: Value,
}

pub async fn send(router: &Router, request: Request<Body>) -> Reply {
    let response = router.clone().oneshot(request).await.unwrap();
    let status = response.status();
    let headers = response.headers().clone();
    let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let body = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap()
    };
    Reply {
        status,
        headers,
        body,
    }
}

pub fn request(
    method: Method,
    uri: &str,
    cookie: Option<&str>,
    body: Option<Value>,
) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(cookie) = cookie {
        builder = builder.header(COOKIE, cookie);
    }
    match body {
        Some(body) => builder
            .header(CONTENT_TYPE, "application/json")
            .body(Body::from(body.to_string()))
            .unwrap(),
        None => builder.body(Body::empty()).unwrap(),
    }
}

pub fn get(uri: &str, cookie: Option<&str>) -> Request<Body> {
    request(Method::GET, uri, cookie, None)
}

pub fn post(uri: &str, cookie: Option<&str>, body: Value) -> Request<Body> {
    request(Method::POST, uri, cookie, Some(body))
}

pub fn delete(uri: &str, cookie: Option<&str>) -> Request<Body> {
    request(Method::DELETE, uri, cookie, None)
}

/// A request that carries an `Authorization` header and no session.
pub fn with_authorization(
    method: Method,
    uri: &str,
    authorization: &str,
    body: Option<Value>,
) -> Request<Body> {
    let mut request = request(method, uri, None, body);
    request
        .headers_mut()
        .insert(AUTHORIZATION, authorization.parse().unwrap());
    request
}

/// The `name=value` pair from a `Set-Cookie` header.
pub fn session_cookie(reply: &Reply) -> String {
    let header = reply.headers[SET_COOKIE].to_str().unwrap();
    header.split(';').next().unwrap().to_string()
}

/// Create the first user. Returns that user's session cookie.
pub async fn sign_up(router: &Router) -> String {
    let reply = send(
        router,
        post(
            "/api/v1/users/create-first-user",
            None,
            json!({"email": EMAIL, "password": PASSWORD}),
        ),
    )
    .await;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    session_cookie(&reply)
}

pub fn app() -> (Router, TestApp) {
    let app = test_app();
    (router(app.state.clone(), false), app)
}
