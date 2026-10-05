//! The HTTP application: routes and layers.
//!
//! `/api/v1` is the API and `/health` is the liveness check. Every route is
//! registered once, here, with its OpenAPI description, so the served routes
//! and the published document cannot drift apart. Every other GET is the UI.

use std::any::Any;

use axum::Router;
use axum::extract::{Request, State};
use axum::http::{Method, StatusCode};
use axum::response::{IntoResponse, Response};
use tower_http::catch_panic::CatchPanicLayer;
use tower_http::trace::{DefaultMakeSpan, TraceLayer};
use utoipa::openapi::security::{HttpAuthScheme, HttpBuilder, SecurityScheme};
use utoipa::{Modify, OpenApi};
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::error::ApiError;
use crate::features::{
    admin, agent_diagnostics, api_keys, auth, cli_sign_in, config, evaluation, evaluation_tokens,
    execution_resolution, health, otel_spans, trace_evidence,
};
use crate::state::AppState;

#[derive(OpenApi)]
#[openapi(
    info(
        title = "Junjo AI Studio",
        description = "The Junjo AI Studio API: observability, execution evidence, and evaluation control."
    ),
    modifiers(&SecuritySchemes)
)]
struct ApiDocument;

/// The name operations use to say they accept a developer access token.
const EVALUATION_CONTROL_TOKEN_SCHEME: &str = "EvaluationControlToken";

struct SecuritySchemes;

impl Modify for SecuritySchemes {
    fn modify(&self, openapi: &mut utoipa::openapi::OpenApi) {
        let scheme = HttpBuilder::new()
            .scheme(HttpAuthScheme::Bearer)
            .description(Some(
                "A separately scoped Studio evaluation-control token. \
                 Studio ingestion API keys are not accepted.",
            ))
            .build();
        openapi
            .components
            .get_or_insert_default()
            .add_security_scheme(
                EVALUATION_CONTROL_TOKEN_SCHEME,
                SecurityScheme::Http(scheme),
            );
    }
}

/// Every documented route, without state or layers. Each feature owns its
/// routes; this is the one place they are assembled under `/api/v1`.
fn documented_routes() -> OpenApiRouter<AppState> {
    let api = OpenApiRouter::new()
        .merge(auth::routes())
        .merge(api_keys::routes())
        .merge(evaluation_tokens::routes())
        .merge(cli_sign_in::routes())
        .merge(evaluation::routes())
        .merge(execution_resolution::routes())
        .merge(agent_diagnostics::routes())
        .merge(trace_evidence::routes())
        .merge(otel_spans::routes())
        .merge(admin::routes())
        .merge(config::routes());

    OpenApiRouter::with_openapi(ApiDocument::openapi())
        .routes(routes!(health::health))
        .nest("/api/v1", api)
}

/// The generated OpenAPI description of every route.
pub fn openapi() -> utoipa::openapi::OpenApi {
    documented_routes().into_openapi()
}

pub fn router(state: AppState, is_production: bool) -> Router {
    let (routes, _document) = documented_routes().split_for_parts();
    routes
        .fallback(not_a_route)
        .method_not_allowed_fallback(method_not_allowed)
        .layer(auth::session_layer(
            state.session_store.clone(),
            is_production,
        ))
        .layer(CatchPanicLayer::custom(panic_response))
        // The request span is on at the default log level, so a line logged
        // while a request is handled names its method and path. The layer's
        // own request and response lines stay at debug.
        .layer(
            TraceLayer::new_for_http()
                .make_span_with(DefaultMakeSpan::new().level(tracing::Level::INFO)),
        )
        .with_state(state)
}

/// A request for no API route. A GET outside `/api` is the UI, when this
/// process serves it: a file of the build, or the app itself. Everything
/// else is not found.
async fn not_a_route(State(state): State<AppState>, request: Request) -> Response {
    let path = request.uri().path();
    let is_api = path == "/api" || path.starts_with("/api/");
    let is_read = matches!(*request.method(), Method::GET | Method::HEAD);
    match &state.ui {
        Some(ui) if is_read && !is_api => ui.serve(request).await,
        _ => ApiError::not_found("Not found").into_response(),
    }
}

async fn method_not_allowed() -> ApiError {
    ApiError::new(
        StatusCode::METHOD_NOT_ALLOWED,
        "method_not_allowed",
        "Method not allowed",
    )
}

/// An unhandled panic becomes the standard 500 body instead of a dropped
/// connection.
fn panic_response(panic: Box<dyn Any + Send + 'static>) -> Response {
    let detail = panic
        .downcast_ref::<String>()
        .map(String::as_str)
        .or_else(|| panic.downcast_ref::<&str>().copied())
        .unwrap_or("unknown panic");
    tracing::error!(detail, "unhandled HTTP request panic");
    ApiError::internal().into_response()
}

#[cfg(test)]
mod tests {
    use axum::body::Body;
    use axum::http::header::{CONTENT_TYPE, SET_COOKIE};
    use axum::http::{Method, Request, StatusCode};
    use serde_json::json;

    use super::*;
    use crate::test_http::{
        EMAIL, PASSWORD, app, get, post, request, send, session_cookie, sign_up,
    };
    use crate::test_support::test_app;

    #[tokio::test]
    async fn health_reports_status_and_version() {
        let (router, _app) = app();
        let reply = send(&router, get("/health", None)).await;
        assert_eq!(reply.status, StatusCode::OK);
        assert_eq!(
            reply.body,
            json!({
                "status": "ok",
                "version": env!("CARGO_PKG_VERSION"),
                "app_name": "Junjo AI Studio",
            })
        );
        // Liveness never touches the session store.
        assert!(!reply.headers.contains_key(SET_COOKIE));
    }

    #[tokio::test]
    async fn a_known_path_with_another_method_is_a_json_405() {
        let (router, _app) = app();
        for (method, uri) in [
            (Method::DELETE, "/health"),
            (Method::PUT, "/api/v1/sign-in"),
            (Method::POST, "/api/v1/observability/services"),
        ] {
            let reply = send(&router, request(method.clone(), uri, None, None)).await;
            assert_eq!(
                reply.status,
                StatusCode::METHOD_NOT_ALLOWED,
                "{method} {uri}"
            );
            assert_eq!(
                reply.body,
                json!({"code": "method_not_allowed", "message": "Method not allowed"}),
                "{method} {uri}"
            );
            // The caller is still told which methods the path takes.
            assert!(reply.headers.contains_key("allow"), "{method} {uri}");
        }
    }

    #[tokio::test]
    async fn an_unknown_path_is_a_json_404() {
        let (router, _app) = app();
        let reply = send(&router, get("/api/v1/unknown", None)).await;
        assert_eq!(reply.status, StatusCode::NOT_FOUND);
        assert_eq!(
            reply.body,
            json!({"code": "not_found", "message": "Not found"})
        );
    }

    #[tokio::test]
    async fn first_user_setup_signs_in_and_blocks_a_second_first_user() {
        let (router, _app) = app();
        let before = send(&router, get("/api/v1/users/db-has-users", None)).await;
        assert_eq!(before.body, json!({"users_exist": false}));

        let created = send(
            &router,
            post(
                "/api/v1/users/create-first-user",
                None,
                json!({"email": " Owner@Example.COM ", "password": PASSWORD}),
            ),
        )
        .await;
        assert_eq!(created.status, StatusCode::OK);
        assert_eq!(
            created.body,
            json!({"message": "First user created successfully"})
        );
        let cookie = session_cookie(&created);

        // The address is stored and compared in lowercase.
        let signed_in = send(&router, get("/api/v1/auth-test", Some(&cookie))).await;
        assert_eq!(signed_in.status, StatusCode::OK);
        assert_eq!(signed_in.body, json!({"user_email": "owner@example.com"}));

        let after = send(&router, get("/api/v1/users/db-has-users", None)).await;
        assert_eq!(after.body, json!({"users_exist": true}));

        let second = send(
            &router,
            post(
                "/api/v1/users/create-first-user",
                None,
                json!({"email": "other@example.com", "password": PASSWORD}),
            ),
        )
        .await;
        assert_eq!(second.status, StatusCode::BAD_REQUEST);
        assert_eq!(
            second.body,
            json!({
                "code": "users_already_exist",
                "message": "Users already exist, cannot create first user",
            })
        );
    }

    #[tokio::test]
    async fn the_session_cookie_is_opaque_host_only_and_strict() {
        for (is_production, expects_secure) in [(false, false), (true, true)] {
            // A fresh database per mode: first-user setup works once.
            let app = test_app();
            let router = router(app.state.clone(), is_production);
            let reply = send(
                &router,
                post(
                    "/api/v1/users/create-first-user",
                    None,
                    json!({"email": EMAIL, "password": PASSWORD}),
                ),
            )
            .await;
            let header = reply.headers[SET_COOKIE].to_str().unwrap().to_string();
            assert!(header.starts_with("junjo_session="), "{header}");
            assert!(header.contains("HttpOnly"), "{header}");
            assert!(header.contains("SameSite=Strict"), "{header}");
            assert!(header.contains("Path=/"), "{header}");
            assert!(header.contains("Max-Age=2592000"), "{header}");
            assert!(!header.contains("Domain="), "{header}");
            assert_eq!(header.contains("Secure"), expects_secure, "{header}");
            assert!(!header.contains("owner"), "{header}");
        }
    }

    /// The routes anyone may call: liveness, first-user setup, sign-in, the
    /// deployment facts shown before sign-in, and the two calls a terminal
    /// makes to sign the CLI in. A terminal has no credential when it
    /// starts, and its device code is the credential when it collects.
    const PUBLIC_ROUTES: [(&str, &str); 7] = [
        ("get", "/health"),
        ("get", "/api/v1/users/db-has-users"),
        ("post", "/api/v1/users/create-first-user"),
        ("post", "/api/v1/sign-in"),
        ("get", "/api/v1/config"),
        ("post", "/api/v1/cli-sign-ins"),
        ("post", "/api/v1/cli-sign-ins/token"),
    ];

    /// The routes that take a developer access token and never a session: a
    /// token describing and revoking itself.
    const TOKEN_ONLY_ROUTES: [(&str, &str); 2] = [
        ("get", "/api/v1/evaluation-tokens/current"),
        ("delete", "/api/v1/evaluation-tokens/current"),
    ];

    #[tokio::test]
    async fn every_route_that_is_not_public_requires_a_credential() {
        let (router, _app) = app();
        let document = crate::openapi::published(&openapi()).unwrap();
        let mut protected = 0;
        for (path, operations) in document["paths"].as_object().unwrap() {
            for method in operations.as_object().unwrap().keys() {
                // Parameters are sent as placeholders and the body as an
                // empty object: the credential is checked before either.
                let uri = path.replace(['{', '}'], "");
                let reply = send(
                    &router,
                    request(
                        method.to_uppercase().parse().unwrap(),
                        &uri,
                        None,
                        Some(json!({})),
                    ),
                )
                .await;
                if PUBLIC_ROUTES.contains(&(method.as_str(), path.as_str())) {
                    assert_ne!(reply.status, StatusCode::UNAUTHORIZED, "{method} {path}");
                    continue;
                }
                assert_eq!(reply.status, StatusCode::UNAUTHORIZED, "{method} {path}");
                let message = if TOKEN_ONLY_ROUTES.contains(&(method.as_str(), path.as_str())) {
                    "Missing evaluation token authorization header"
                } else {
                    "No valid session"
                };
                assert_eq!(
                    reply.body,
                    json!({"code": "unauthorized", "message": message}),
                    "{method} {path}"
                );
                protected += 1;
            }
        }
        // The check found the routes: this is not an empty loop.
        assert!(protected >= 20, "{protected} protected routes");
    }

    #[tokio::test]
    async fn a_forged_or_malformed_session_cookie_is_no_session() {
        let (router, _app) = app();
        let cookie = sign_up(&router).await;
        let tampered = format!("{cookie}x");
        for cookie in [
            "junjo_session=AAAAAAAAAAAAAAAAAAAAAA",
            "junjo_session=",
            "junjo_session=not a session identifier",
            tampered.as_str(),
        ] {
            let reply = send(&router, get("/api/v1/auth-test", Some(cookie))).await;
            assert_eq!(reply.status, StatusCode::UNAUTHORIZED, "{cookie}");
        }
    }

    #[tokio::test]
    async fn an_authenticated_read_does_not_write_the_session() {
        let (router, _app) = app();
        let cookie = sign_up(&router).await;
        let reply = send(&router, get("/api/v1/auth-test", Some(&cookie))).await;
        assert_eq!(reply.status, StatusCode::OK);
        // No renewed cookie means the session was not saved.
        assert!(!reply.headers.contains_key(SET_COOKIE));
    }

    #[tokio::test]
    async fn a_session_is_renewed_once_its_last_renewal_is_a_day_old() {
        let (router, app) = app();
        let cookie = sign_up(&router).await;
        app.state
            .application_db
            .writer
            .call(|connection| {
                connection.execute(
                    "UPDATE sessions SET data = json_set(data, '$.renewed_at', 0)",
                    [],
                )
            })
            .await
            .unwrap();

        let renewed = send(&router, get("/api/v1/auth-test", Some(&cookie))).await;
        assert_eq!(renewed.status, StatusCode::OK);
        assert_eq!(session_cookie(&renewed), cookie);

        let settled = send(&router, get("/api/v1/auth-test", Some(&cookie))).await;
        assert!(!settled.headers.contains_key(SET_COOKIE));
    }

    #[tokio::test]
    async fn a_deleted_or_inactive_user_loses_access() {
        for statement in ["DELETE FROM users", "UPDATE users SET is_active = 0"] {
            let (router, app) = app();
            let cookie = sign_up(&router).await;
            app.state
                .application_db
                .writer
                .call(move |connection| connection.execute(statement, []))
                .await
                .unwrap();
            let reply = send(&router, get("/api/v1/auth-test", Some(&cookie))).await;
            assert_eq!(reply.status, StatusCode::UNAUTHORIZED, "{statement}");
            assert_eq!(reply.body["message"], "User not found");
        }
    }

    #[tokio::test]
    async fn invalid_requests_are_422_with_the_standard_body() {
        let (router, _app) = app();
        let long_password = "x".repeat(73);
        // The message names the member and the reason. It is shown to a user.
        let cases = [
            (
                json!({"email": "not-an-email", "password": PASSWORD}),
                "email: value is not a valid email address",
            ),
            (
                json!({"email": EMAIL, "password": "short"}),
                "password: Password must be at least 8 characters",
            ),
            (
                json!({"email": EMAIL, "password": long_password}),
                "password: Password must be at most 72 bytes",
            ),
            (json!({"email": EMAIL}), "missing field `password`"),
            (
                json!({"email": 7, "password": PASSWORD}),
                "email: invalid type: integer `7`, expected a string",
            ),
        ];
        for (body, message) in cases {
            let reply = send(
                &router,
                post("/api/v1/users/create-first-user", None, body.clone()),
            )
            .await;
            assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
            assert_eq!(
                reply.body,
                json!({"code": "invalid_request", "message": message}),
                "{body}"
            );
        }

        let malformed = Request::builder()
            .method(Method::POST)
            .uri("/api/v1/users/create-first-user")
            .header(CONTENT_TYPE, "application/json")
            .body(Body::from("{not json"))
            .unwrap();
        let reply = send(&router, malformed).await;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(reply.body["code"], "invalid_request");

        let no_content_type = Request::builder()
            .method(Method::POST)
            .uri("/api/v1/users/create-first-user")
            .body(Body::from(
                json!({"email": EMAIL, "password": PASSWORD}).to_string(),
            ))
            .unwrap();
        let reply = send(&router, no_content_type).await;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY);

        // Nothing above created a user.
        let users = send(&router, get("/api/v1/users/db-has-users", None)).await;
        assert_eq!(users.body, json!({"users_exist": false}));
    }
}
