//! Security and contract tests for developer access tokens.

use axum::http::header::WWW_AUTHENTICATE;
use axum::http::{Method, StatusCode};
use axum::routing::get as route_get;
use axum::{Json, Router};
use chrono::{Duration, Utc};
use rusqlite::params;
use serde_json::{Value, json};

use super::access::{EvaluationReadAccess, EvaluationWriteAccess, EvidenceReadAccess};
use crate::features::auth::{self, AuthenticatedUser};
use crate::test_http::{Reply, app, delete, get, post, request, send, sign_up, with_authorization};
use crate::test_support::TestApp;

const TOKENS: &str = "/api/v1/evaluation-tokens";
/// Where a token describes and revokes itself.
const CURRENT: &str = "/api/v1/evaluation-tokens/current";
const PROBES: [(&str, &str); 3] = [
    ("/evaluation-read", "evaluation:read"),
    ("/evaluation-write", "evaluation:write"),
    ("/evidence-read", "evidence:read"),
];

async fn create_token(router: &Router, cookie: &str, name: &str, scopes: &[&str]) -> Value {
    let reply = send(
        router,
        post(
            TOKENS,
            Some(cookie),
            json!({"name": name, "scopes": scopes}),
        ),
    )
    .await;
    assert_eq!(reply.status, StatusCode::CREATED, "{}", reply.body);
    reply.body
}

fn caller(user: AuthenticatedUser) -> Json<Value> {
    Json(json!({"email": user.email, "audit_id": user.audit_id}))
}

/// One route per scope, behind the application's session layer. Only write
/// access says who the caller is.
fn scope_probes(app: &TestApp) -> Router {
    Router::new()
        .route(
            "/evaluation-read",
            route_get(|_: EvaluationReadAccess| async { Json(json!({})) }),
        )
        .route(
            "/evaluation-write",
            route_get(|access: EvaluationWriteAccess| async move { caller(access.0) }),
        )
        .route(
            "/evidence-read",
            route_get(|_: EvidenceReadAccess| async { Json(json!({})) }),
        )
        .layer(auth::session_layer(app.state.session_store.clone(), false))
        .with_state(app.state.clone())
}

async fn probe(probes: &Router, uri: &str, authorization: &str) -> Reply {
    send(
        probes,
        with_authorization(Method::GET, uri, authorization, None),
    )
    .await
}

fn bearer(token: &Value) -> String {
    format!("Bearer {}", token["token"].as_str().unwrap())
}

fn assert_unauthorized(reply: &Reply, message: &str) {
    assert_eq!(reply.status, StatusCode::UNAUTHORIZED, "{}", reply.body);
    assert_eq!(
        reply.body,
        json!({"code": "unauthorized", "message": message})
    );
    assert_eq!(reply.headers[WWW_AUTHENTICATE], "Bearer");
}

#[tokio::test]
async fn a_token_is_recoverable_from_the_management_routes() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let created = create_token(
        &router,
        &cookie,
        "Coding agent",
        &["evaluation:write", "evaluation:read", "evidence:read"],
    )
    .await;

    let token = created["token"].as_str().unwrap().to_string();
    assert!(token.starts_with("jcli_"), "{token}");
    assert_eq!(token.len(), 69);
    assert_eq!(
        created.as_object().unwrap().keys().collect::<Vec<_>>(),
        [
            "id",
            "name",
            "token",
            "scopes",
            "expires_at",
            "created_by_user_id",
            "created_at"
        ]
    );
    assert_eq!(created["name"], "Coding agent");
    // Scopes are listed in one order, whatever order they were requested in.
    assert_eq!(
        created["scopes"],
        json!(["evaluation:read", "evaluation:write", "evidence:read"])
    );
    assert_eq!(created["expires_at"], Value::Null);
    assert!(created["created_by_user_id"].is_string());

    let listed = send(&router, get(TOKENS, Some(&cookie))).await;
    assert_eq!(listed.status, StatusCode::OK);
    assert_eq!(
        listed.body,
        json!({"items": [created], "next_cursor": null})
    );

    let id = created["id"].as_str().unwrap().to_string();
    let stored: String = app
        .state
        .application_db
        .reader
        .call(move |connection| {
            connection.query_row(
                "SELECT token FROM evaluation_tokens WHERE id = ?1",
                params![id],
                |row| row.get(0),
            )
        })
        .await
        .unwrap();
    assert_eq!(stored, token);
}

#[tokio::test]
async fn the_listing_is_keyset_paginated_and_deletion_is_explicit() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    let first = create_token(&router, &cookie, "First", &["evaluation:read"]).await;
    let second = create_token(&router, &cookie, "Second", &["evidence:read"]).await;

    let first_page = send(&router, get(&format!("{TOKENS}?limit=1"), Some(&cookie))).await;
    assert_eq!(first_page.status, StatusCode::OK);
    assert_eq!(first_page.body["items"].as_array().unwrap().len(), 1);
    let cursor = first_page.body["next_cursor"].as_str().unwrap();
    let second_page = send(
        &router,
        get(&format!("{TOKENS}?limit=1&cursor={cursor}"), Some(&cookie)),
    )
    .await;
    assert_eq!(second_page.status, StatusCode::OK);
    assert_eq!(second_page.body["next_cursor"], Value::Null);
    let mut page_ids = vec![
        first_page.body["items"][0]["id"].clone(),
        second_page.body["items"][0]["id"].clone(),
    ];
    page_ids.sort_by_key(Value::to_string);
    let mut created_ids = vec![first["id"].clone(), second["id"].clone()];
    created_ids.sort_by_key(Value::to_string);
    assert_eq!(page_ids, created_ids);

    let malformed = send(
        &router,
        get(&format!("{TOKENS}?cursor=____"), Some(&cookie)),
    )
    .await;
    assert_eq!(malformed.status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(
        malformed.body,
        json!({"code": "invalid_request", "message": "Invalid pagination cursor"})
    );
    for query in ["cursor=", "limit=0", "limit=101", "limit=many"] {
        let reply = send(&router, get(&format!("{TOKENS}?{query}"), Some(&cookie))).await;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY, "{query}");
        assert_eq!(reply.body["code"], "invalid_request", "{query}");
    }

    let first_uri = format!("{TOKENS}/{}", first["id"].as_str().unwrap());
    let deleted = send(&router, delete(&first_uri, Some(&cookie))).await;
    assert_eq!(deleted.status, StatusCode::NO_CONTENT);
    let deleted_again = send(&router, delete(&first_uri, Some(&cookie))).await;
    assert_eq!(deleted_again.status, StatusCode::NOT_FOUND);
    assert_eq!(
        deleted_again.body,
        json!({"code": "not_found", "message": "Access token not found"})
    );
    let missing = send(&router, delete(&format!("{TOKENS}/missing"), Some(&cookie))).await;
    assert_eq!(missing.status, StatusCode::NOT_FOUND);
    let too_long = send(
        &router,
        delete(&format!("{TOKENS}/{}", "a".repeat(65)), Some(&cookie)),
    )
    .await;
    assert_eq!(too_long.status, StatusCode::UNPROCESSABLE_ENTITY);
}

#[tokio::test]
async fn token_management_requires_a_session_not_a_token() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    let token = create_token(
        &router,
        &cookie,
        "Cannot manage credentials",
        &["evaluation:read", "evaluation:write", "evidence:read"],
    )
    .await;

    for (method, uri, body) in [
        (Method::GET, TOKENS.to_string(), None),
        (
            Method::POST,
            TOKENS.to_string(),
            Some(json!({"name": "Another", "scopes": ["evaluation:read"]})),
        ),
        (
            Method::DELETE,
            format!("{TOKENS}/{}", token["id"].as_str().unwrap()),
            None,
        ),
    ] {
        let reply = send(
            &router,
            with_authorization(method.clone(), &uri, &bearer(&token), body),
        )
        .await;
        assert_eq!(reply.status, StatusCode::UNAUTHORIZED, "{method} {uri}");
    }
}

#[tokio::test]
async fn evaluation_read_write_and_evidence_scopes_are_distinct() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let probes = scope_probes(&app);

    for (_, held) in PROBES {
        let token = create_token(&router, &cookie, held, &[held]).await;
        for (uri, required) in PROBES {
            let reply = probe(&probes, uri, &bearer(&token)).await;
            if required == held {
                assert_eq!(reply.status, StatusCode::OK, "{held} on {uri}");
                if uri == "/evaluation-write" {
                    // A change made with a token is attributed to the token
                    // and to the user who created it.
                    assert_eq!(
                        reply.body,
                        json!({
                            "email": "owner@example.com",
                            "audit_id": format!(
                                "evaluation-token:{}",
                                token["id"].as_str().unwrap()
                            ),
                        })
                    );
                }
            } else {
                assert_eq!(reply.status, StatusCode::FORBIDDEN, "{held} on {uri}");
                assert_eq!(
                    reply.body,
                    json!({
                        "code": "insufficient_evaluation_token_scope",
                        "message": "Evaluation token lacks the required scope.",
                        "missing_scopes": [required],
                    }),
                    "{held} on {uri}"
                );
            }
        }
    }
}

#[tokio::test]
async fn deletion_applies_to_the_next_request() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let probes = scope_probes(&app);
    let token = create_token(&router, &cookie, "Revocable", &["evaluation:read"]).await;

    // Authentication reads through the read-only connection, so it has no
    // cache to invalidate and nothing to write.
    let authorized = probe(&probes, "/evaluation-read", &bearer(&token)).await;
    assert_eq!(authorized.status, StatusCode::OK);

    let uri = format!("{TOKENS}/{}", token["id"].as_str().unwrap());
    let deleted = send(&router, delete(&uri, Some(&cookie))).await;
    assert_eq!(deleted.status, StatusCode::NO_CONTENT);

    let rejected = probe(&probes, "/evaluation-read", &bearer(&token)).await;
    assert_unauthorized(&rejected, "Invalid or expired evaluation token");
}

#[tokio::test]
async fn expired_unknown_and_malformed_credentials_are_rejected() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let probes = scope_probes(&app);

    let in_an_hour = Utc::now() + Duration::hours(1);
    let expiring = send(
        &router,
        post(
            TOKENS,
            Some(&cookie),
            json!({
                "name": "Expiring",
                "scopes": ["evaluation:read"],
                "expires_at": in_an_hour.to_rfc3339(),
            }),
        ),
    )
    .await;
    assert_eq!(expiring.status, StatusCode::CREATED, "{}", expiring.body);
    // The expiry is stored and returned in UTC at whole seconds.
    assert_eq!(
        expiring.body["expires_at"],
        in_an_hour.format("%Y-%m-%dT%H:%M:%SZ").to_string()
    );
    let working = probe(&probes, "/evaluation-read", &bearer(&expiring.body)).await;
    assert_eq!(working.status, StatusCode::OK);

    for (expires_at, message) in [
        (
            (Utc::now() - Duration::seconds(1)).to_rfc3339(),
            "expires_at must be in the future",
        ),
        // A timestamp without an offset names no instant.
        ("2999-01-01T00:00:00".to_string(), ""),
    ] {
        let reply = send(
            &router,
            post(
                TOKENS,
                Some(&cookie),
                json!({"name": "Expired", "scopes": ["evaluation:read"], "expires_at": expires_at}),
            ),
        )
        .await;
        assert_eq!(
            reply.status,
            StatusCode::UNPROCESSABLE_ENTITY,
            "{expires_at}"
        );
        assert_eq!(reply.body["code"], "invalid_request");
        assert!(
            reply.body["message"].as_str().unwrap().contains(message),
            "{}",
            reply.body
        );
    }

    let id = expiring.body["id"].as_str().unwrap().to_string();
    app.state
        .application_db
        .writer
        .call(move |connection| {
            connection.execute(
                "UPDATE evaluation_tokens SET expires_at = '2020-01-01T00:00:00Z' WHERE id = ?1",
                params![id],
            )
        })
        .await
        .unwrap();
    let expired = probe(&probes, "/evaluation-read", &bearer(&expiring.body)).await;
    assert_unauthorized(&expired, "Invalid or expired evaluation token");

    let unknown = probe(
        &probes,
        "/evaluation-read",
        "Bearer token-not-present-in-the-table",
    )
    .await;
    assert_unauthorized(&unknown, "Invalid or expired evaluation token");

    // An Authorization header is never ignored in favor of a session.
    for authorization in ["Basic abc", "Bearer", "jcli_without_a_scheme"] {
        let mut request = with_authorization(Method::GET, "/evaluation-read", authorization, None);
        request
            .headers_mut()
            .insert("cookie", cookie.parse().unwrap());
        let reply = send(&probes, request).await;
        assert_unauthorized(&reply, "Invalid evaluation token authorization header");
    }
}

#[tokio::test]
async fn a_token_stops_working_when_its_creator_is_inactive_or_deleted() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let probes = scope_probes(&app);
    let token = create_token(&router, &cookie, "Orphaned", &["evidence:read"]).await;
    let set_users = |statement: &'static str| {
        let writer = app.state.application_db.writer.clone();
        async move {
            writer
                .call(move |connection| connection.execute(statement, []))
                .await
                .unwrap();
        }
    };

    set_users("UPDATE users SET is_active = 0").await;
    let inactive = probe(&probes, "/evidence-read", &bearer(&token)).await;
    assert_unauthorized(&inactive, "Invalid or expired evaluation token");

    set_users("UPDATE users SET is_active = 1").await;
    let active = probe(&probes, "/evidence-read", &bearer(&token)).await;
    assert_eq!(active.status, StatusCode::OK);

    // Deleting the creator keeps the token row and clears its creator.
    set_users("DELETE FROM users").await;
    let orphaned = probe(&probes, "/evidence-read", &bearer(&token)).await;
    assert_unauthorized(&orphaned, "Invalid or expired evaluation token");
    let creator: Option<String> = app
        .state
        .application_db
        .reader
        .call(|connection| {
            connection.query_row(
                "SELECT created_by_user_id FROM evaluation_tokens",
                [],
                |row| row.get(0),
            )
        })
        .await
        .unwrap();
    assert_eq!(creator, None);
}

#[tokio::test]
async fn a_session_is_accepted_on_token_protected_routes() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let probes = scope_probes(&app);

    for (uri, _) in PROBES {
        let signed_in = send(&probes, get(uri, Some(&cookie))).await;
        assert_eq!(signed_in.status, StatusCode::OK, "{uri}");
        if uri == "/evaluation-write" {
            assert_eq!(signed_in.body["email"], "owner@example.com");
        }

        let anonymous = send(&probes, get(uri, None)).await;
        assert_eq!(anonymous.status, StatusCode::UNAUTHORIZED, "{uri}");
        assert_eq!(
            anonymous.body,
            json!({"code": "unauthorized", "message": "No valid session"})
        );
    }
}

#[tokio::test]
async fn an_invalid_token_request_is_refused() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;

    for body in [
        json!({"name": "   ", "scopes": ["evaluation:read"]}),
        json!({"name": " padded ", "scopes": ["evaluation:read"]}),
        json!({"name": "", "scopes": ["evaluation:read"]}),
        json!({"name": "é".repeat(129), "scopes": ["evaluation:read"]}),
        json!({"name": "No scopes", "scopes": []}),
        json!({"name": "Twice", "scopes": ["evaluation:read", "evaluation:read"]}),
        json!({"name": "Unknown", "scopes": ["evaluation:admin"]}),
        json!({"name": "Extra", "scopes": ["evaluation:read"], "prefix": "jcli_"}),
        json!({"scopes": ["evaluation:read"]}),
    ] {
        let reply = send(&router, post(TOKENS, Some(&cookie), body.clone())).await;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
        assert_eq!(reply.body["code"], "invalid_request", "{body}");
    }

    // 256 bytes is the longest name.
    let longest = send(
        &router,
        post(
            TOKENS,
            Some(&cookie),
            json!({"name": "é".repeat(128), "scopes": ["evaluation:read"]}),
        ),
    )
    .await;
    assert_eq!(longest.status, StatusCode::CREATED, "{}", longest.body);
}

/// Call a route on which a token acts on itself, with that token.
async fn as_itself(router: &Router, method: Method, token: &Value) -> Reply {
    send(
        router,
        with_authorization(method, CURRENT, &bearer(token), None),
    )
    .await
}

#[tokio::test]
async fn a_token_describes_itself_without_repeating_its_value() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    // Any valid token may ask: no scope is the scope of this route.
    let token = create_token(&router, &cookie, "Asks about itself", &["evidence:read"]).await;

    let current = as_itself(&router, Method::GET, &token).await;
    assert_eq!(current.status, StatusCode::OK, "{}", current.body);
    assert_eq!(
        current.body,
        json!({
            "id": token["id"],
            "name": "Asks about itself",
            "scopes": ["evidence:read"],
            "expires_at": null,
            "created_at": token["created_at"],
        })
    );
    assert_eq!(
        current.body.as_object().unwrap().keys().collect::<Vec<_>>(),
        ["id", "name", "scopes", "expires_at", "created_at"]
    );

    // A token that expires says when.
    let in_an_hour = Utc::now() + Duration::hours(1);
    let expiring = send(
        &router,
        post(
            TOKENS,
            Some(&cookie),
            json!({
                "name": "Expiring",
                "scopes": ["evaluation:write", "evaluation:read"],
                "expires_at": in_an_hour.to_rfc3339(),
            }),
        ),
    )
    .await;
    assert_eq!(expiring.status, StatusCode::CREATED, "{}", expiring.body);
    let current = as_itself(&router, Method::GET, &expiring.body).await;
    assert_eq!(
        current.body,
        json!({
            "id": expiring.body["id"],
            "name": "Expiring",
            "scopes": ["evaluation:read", "evaluation:write"],
            "expires_at": in_an_hour.format("%Y-%m-%dT%H:%M:%SZ").to_string(),
            "created_at": expiring.body["created_at"],
        })
    );

    // A session beside the token changes nothing: the token is judged.
    let mut both = with_authorization(Method::GET, CURRENT, &bearer(&token), None);
    both.headers_mut().insert("cookie", cookie.parse().unwrap());
    let reply = send(&router, both).await;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(reply.body["id"], token["id"]);
}

#[tokio::test]
async fn a_token_revokes_itself_and_stops_working_at_once() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    let token = create_token(&router, &cookie, "Signs out", &["evaluation:read"]).await;
    let other = create_token(&router, &cookie, "Stays", &["evaluation:read"]).await;
    let datasets = "/api/v1/evaluation/datasets";

    let working = send(
        &router,
        with_authorization(Method::GET, datasets, &bearer(&token), None),
    )
    .await;
    assert_eq!(working.status, StatusCode::OK, "{}", working.body);

    let revoked = as_itself(&router, Method::DELETE, &token).await;
    assert_eq!(revoked.status, StatusCode::NO_CONTENT, "{}", revoked.body);
    assert_eq!(revoked.body, Value::Null);

    // It authenticates nothing any more, itself included.
    let refused = send(
        &router,
        with_authorization(Method::GET, datasets, &bearer(&token), None),
    )
    .await;
    assert_unauthorized(&refused, "Invalid or expired evaluation token");
    for method in [Method::GET, Method::DELETE] {
        let reply = as_itself(&router, method, &token).await;
        assert_unauthorized(&reply, "Invalid or expired evaluation token");
    }

    // Only that token is gone.
    let listed = send(&router, get(TOKENS, Some(&cookie))).await;
    assert_eq!(listed.body["items"], json!([other]));
    let current = as_itself(&router, Method::GET, &other).await;
    assert_eq!(current.status, StatusCode::OK, "{}", current.body);
}

#[tokio::test]
async fn a_session_is_not_a_credential_for_a_token_acting_on_itself() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    let token = create_token(&router, &cookie, "Untouched", &["evaluation:read"]).await;

    for method in [Method::GET, Method::DELETE] {
        let signed_in = send(
            &router,
            request(method.clone(), CURRENT, Some(&cookie), None),
        )
        .await;
        assert_unauthorized(&signed_in, "Missing evaluation token authorization header");
        let anonymous = send(&router, request(method.clone(), CURRENT, None, None)).await;
        assert_unauthorized(&anonymous, "Missing evaluation token authorization header");

        // A header that is not a bearer credential is not ignored in favor
        // of the session either.
        let mut malformed = with_authorization(method.clone(), CURRENT, "Basic abc", None);
        malformed
            .headers_mut()
            .insert("cookie", cookie.parse().unwrap());
        let reply = send(&router, malformed).await;
        assert_unauthorized(&reply, "Invalid evaluation token authorization header");

        let unknown = send(
            &router,
            with_authorization(
                method,
                CURRENT,
                "Bearer token-not-present-in-the-table",
                None,
            ),
        )
        .await;
        assert_unauthorized(&unknown, "Invalid or expired evaluation token");
    }

    // The session deleted nothing through this route.
    let listed = send(&router, get(TOKENS, Some(&cookie))).await;
    assert_eq!(listed.body["items"], json!([token]));
}

#[tokio::test]
async fn an_expired_token_and_a_token_of_an_inactive_user_cannot_act_on_themselves() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let token = create_token(&router, &cookie, "Lapses", &["evaluation:read"]).await;
    let execute = |statement: &'static str| {
        let writer = app.state.application_db.writer.clone();
        async move {
            writer
                .call(move |connection| connection.execute(statement, []))
                .await
                .unwrap();
        }
    };
    let stored_tokens = || {
        let reader = app.state.application_db.reader.clone();
        async move {
            reader
                .call(|connection| {
                    connection.query_row("SELECT COUNT(*) FROM evaluation_tokens", [], |row| {
                        row.get::<_, i64>(0)
                    })
                })
                .await
                .unwrap()
        }
    };

    execute("UPDATE evaluation_tokens SET expires_at = '2020-01-01T00:00:00Z'").await;
    for method in [Method::GET, Method::DELETE] {
        let expired = as_itself(&router, method, &token).await;
        assert_unauthorized(&expired, "Invalid or expired evaluation token");
    }

    execute("UPDATE evaluation_tokens SET expires_at = NULL").await;
    execute("UPDATE users SET is_active = 0").await;
    for method in [Method::GET, Method::DELETE] {
        let inactive = as_itself(&router, method, &token).await;
        assert_unauthorized(&inactive, "Invalid or expired evaluation token");
    }

    // A refused request revoked nothing: the token works again with its user.
    assert_eq!(stored_tokens().await, 1);
    execute("UPDATE users SET is_active = 1").await;
    let current = as_itself(&router, Method::GET, &token).await;
    assert_eq!(current.status, StatusCode::OK, "{}", current.body);

    // A token whose creator is deleted is refused too, and stays stored.
    execute("DELETE FROM users").await;
    for method in [Method::GET, Method::DELETE] {
        let orphaned = as_itself(&router, method, &token).await;
        assert_unauthorized(&orphaned, "Invalid or expired evaluation token");
    }
    assert_eq!(stored_tokens().await, 1);
}

#[test]
fn the_published_document_names_the_routes_of_a_token_acting_on_itself() {
    let document = crate::openapi::published(&crate::app::openapi()).unwrap();
    let current = &document["paths"][CURRENT];
    for (method, operation_id) in [
        ("get", "get_current_evaluation_token"),
        ("delete", "delete_current_evaluation_token"),
    ] {
        let operation = &current[method];
        assert_eq!(operation["operationId"], operation_id, "{method}");
        assert_eq!(
            operation["security"],
            json!([{"EvaluationControlToken": []}]),
            "{method}"
        );
        assert_eq!(operation["requestBody"], Value::Null, "{method}");
    }
    assert_eq!(
        current["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"],
        "#/components/schemas/EvaluationTokenCurrent"
    );
    assert_eq!(
        current["delete"]["responses"]["204"]["content"],
        Value::Null
    );

    let described = &document["components"]["schemas"]["EvaluationTokenCurrent"];
    assert_eq!(
        described["required"],
        json!(["id", "name", "scopes", "expires_at", "created_at"])
    );
    // The token value is not part of what a token is told about itself.
    assert_eq!(described["properties"].as_object().unwrap().len(), 5);
    assert_eq!(described["additionalProperties"], false);

    // Managing tokens stays a session's business: those routes name no
    // token credential.
    for (path, method) in [
        (TOKENS, "get"),
        (TOKENS, "post"),
        ("/api/v1/evaluation-tokens/{token_id}", "delete"),
    ] {
        assert_eq!(
            document["paths"][path][method]["security"],
            Value::Null,
            "{method} {path}"
        );
    }
}
