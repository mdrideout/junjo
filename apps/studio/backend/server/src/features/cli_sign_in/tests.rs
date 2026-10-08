//! The CLI browser sign-in through the router: what the approval page and
//! the `junjo` CLI are built against.

use axum::Router;
use axum::body::Body;
use axum::http::header::SET_COOKIE;
use axum::http::{Method, Request, StatusCode};
use chrono::{DateTime, Utc};
use rusqlite::params;
use serde_json::{Value, json};
use tokio::task::JoinSet;

use super::repo::{self, NewSignIn};
use super::{DeviceCode, UserCode};
use crate::features::evaluation_tokens::TokenScopes;
use crate::test_http::{
    PASSWORD, Reply, app, delete, get, post, request, send, session_cookie, sign_up,
    with_authorization,
};
use crate::test_support::TestApp;
use crate::timestamps::UtcSeconds;

const SIGN_INS: &str = "/api/v1/cli-sign-ins";
const COLLECT: &str = "/api/v1/cli-sign-ins/token";
const TOKENS: &str = "/api/v1/evaluation-tokens";
const CLIENT_NAME: &str = "junjo CLI on laptop";

const PENDING: (&str, &str) = (
    "authorization_pending",
    "The CLI sign-in has not been approved or denied yet",
);
const DENIED: (&str, &str) = ("access_denied", "The CLI sign-in was denied");
const EXPIRED: (&str, &str) = (
    "expired_token",
    "The device code is unknown, already used, or expired",
);

/// Start a CLI sign-in as a terminal does: with no credential.
async fn start(router: &Router, scopes: &[&str]) -> Value {
    let reply = send(
        router,
        post(
            SIGN_INS,
            None,
            json!({"client_name": CLIENT_NAME, "scopes": scopes}),
        ),
    )
    .await;
    assert_eq!(reply.status, StatusCode::CREATED, "{}", reply.body);
    reply.body
}

fn text<'a>(body: &'a Value, member: &str) -> &'a str {
    body[member].as_str().unwrap()
}

fn member_names(body: &Value) -> Vec<&String> {
    body.as_object().unwrap().keys().collect()
}

/// Read a sign-in as the approval page does.
async fn page(router: &Router, cookie: &str, user_code: &str) -> Reply {
    send(
        router,
        get(&format!("{SIGN_INS}/{user_code}"), Some(cookie)),
    )
    .await
}

fn decision(user_code: &str, decision: &str, cookie: Option<&str>) -> Request<Body> {
    request(
        Method::POST,
        &format!("{SIGN_INS}/{user_code}/{decision}"),
        cookie,
        None,
    )
}

async fn approve(router: &Router, cookie: &str, user_code: &str) -> Reply {
    send(router, decision(user_code, "approve", Some(cookie))).await
}

async fn deny(router: &Router, cookie: &str, user_code: &str) -> Reply {
    send(router, decision(user_code, "deny", Some(cookie))).await
}

/// Poll as the CLI does: the device code is the only credential.
async fn collect(router: &Router, device_code: &str) -> Reply {
    send(
        router,
        post(COLLECT, None, json!({"device_code": device_code})),
    )
    .await
}

fn assert_not_collected(reply: &Reply, (code, message): (&str, &str)) {
    assert_eq!(reply.status, StatusCode::BAD_REQUEST, "{}", reply.body);
    assert_eq!(reply.body, json!({"code": code, "message": message}));
}

fn assert_not_found(reply: &Reply) {
    assert_eq!(reply.status, StatusCode::NOT_FOUND, "{}", reply.body);
    assert_eq!(
        reply.body,
        json!({"code": "not_found", "message": "CLI sign-in not found"})
    );
}

async fn listed_tokens(router: &Router, cookie: &str) -> Vec<Value> {
    let listed = send(router, get(TOKENS, Some(cookie))).await;
    assert_eq!(listed.status, StatusCode::OK, "{}", listed.body);
    listed.body["items"].as_array().unwrap().clone()
}

async fn stored_device_codes(app: &TestApp) -> Vec<String> {
    app.state
        .application_db
        .reader
        .call(|connection| {
            connection
                .prepare("SELECT device_code FROM cli_sign_ins ORDER BY device_code")?
                .query_map([], |row| row.get(0))?
                .collect()
        })
        .await
        .unwrap()
}

/// Rewrite a sign-in's timestamps, as if it had started 900 seconds before
/// `expires_at`. No test waits for a sign-in to expire.
async fn set_expiry(app: &TestApp, device_code: &str, expires_at: UtcSeconds) {
    let device_code = device_code.to_string();
    let rewritten = app
        .state
        .application_db
        .writer
        .call(move |connection| {
            connection.execute(
                "UPDATE cli_sign_ins SET created_at = ?2, expires_at = ?3 WHERE device_code = ?1",
                params![device_code, expires_at.plus_seconds(-900), expires_at],
            )
        })
        .await
        .unwrap();
    assert_eq!(rewritten, 1);
}

/// Send every request at once and collect the replies.
async fn send_all(router: &Router, requests: Vec<Request<Body>>) -> Vec<Reply> {
    let mut tasks = JoinSet::new();
    for request in requests {
        let router = router.clone();
        tasks.spawn(async move { send(&router, request).await });
    }
    let mut replies = Vec::new();
    while let Some(reply) = tasks.join_next().await {
        replies.push(reply.unwrap());
    }
    replies
}

#[tokio::test]
async fn an_approved_sign_in_hands_its_token_to_the_cli_once() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;

    // The terminal starts a sign-in. It has no credential and is given none.
    let started = send(
        &router,
        post(
            SIGN_INS,
            None,
            json!({
                "client_name": CLIENT_NAME,
                "scopes": ["evidence:read", "evaluation:read"],
            }),
        ),
    )
    .await;
    assert_eq!(started.status, StatusCode::CREATED, "{}", started.body);
    assert!(!started.headers.contains_key(SET_COOKIE));
    let device_code = text(&started.body, "device_code");
    let user_code = text(&started.body, "user_code");
    assert_eq!(
        started.body,
        json!({
            "device_code": device_code,
            "user_code": user_code,
            "verification_path": "/cli-sign-in",
            "expires_in": 900,
            "interval": 5,
        })
    );
    assert_eq!(
        member_names(&started.body),
        [
            "device_code",
            "user_code",
            "verification_path",
            "expires_in",
            "interval"
        ]
    );
    assert!(device_code.starts_with("jdev_"), "{device_code}");
    assert_eq!(device_code.len(), 69);
    // Two groups of four letters with a hyphen.
    let groups: Vec<&str> = user_code.split('-').collect();
    assert_eq!(groups.len(), 2, "{user_code}");
    for group in groups {
        assert_eq!(group.len(), 4, "{user_code}");
        assert!(
            group
                .chars()
                .all(|letter| "BCDFGHJKLMNPQRSTVWXZ".contains(letter)),
            "{user_code}"
        );
    }

    // The approval page shows what the terminal asked for and until when.
    let shown = page(&router, &cookie, user_code).await;
    assert_eq!(shown.status, StatusCode::OK, "{}", shown.body);
    let expires_at = text(&shown.body, "expires_at");
    assert_eq!(
        shown.body,
        json!({
            "user_code": user_code,
            "client_name": CLIENT_NAME,
            // Scopes are listed in one order, whatever order they were
            // requested in.
            "scopes": ["evaluation:read", "evidence:read"],
            "expires_at": expires_at,
        })
    );
    assert_eq!(
        member_names(&shown.body),
        ["user_code", "client_name", "scopes", "expires_at"]
    );
    // UTC at whole seconds, 900 seconds after the start.
    assert!(
        expires_at.ends_with('Z') && expires_at.len() == 20,
        "{expires_at}"
    );
    let remaining = DateTime::parse_from_rfc3339(expires_at)
        .unwrap()
        .signed_duration_since(Utc::now())
        .num_seconds();
    assert!((880..=900).contains(&remaining), "{remaining}");

    // The person approves. That mints the token and names it.
    let approved = approve(&router, &cookie, user_code).await;
    assert_eq!(approved.status, StatusCode::OK, "{}", approved.body);
    let token_id = text(&approved.body, "token_id");
    assert_eq!(
        approved.body,
        json!({"token_id": token_id, "token_name": CLIENT_NAME})
    );
    assert_eq!(member_names(&approved.body), ["token_id", "token_name"]);

    // A decided sign-in is not pending, so the page no longer finds it.
    assert_not_found(&page(&router, &cookie, user_code).await);
    assert_not_found(&approve(&router, &cookie, user_code).await);
    assert_not_found(&deny(&router, &cookie, user_code).await);

    // The terminal's next poll collects the token.
    let collected = collect(&router, device_code).await;
    assert_eq!(collected.status, StatusCode::OK, "{}", collected.body);
    assert!(!collected.headers.contains_key(SET_COOKIE));
    let access_token = text(&collected.body, "access_token");
    assert_eq!(
        collected.body,
        json!({
            "access_token": access_token,
            "token_type": "bearer",
            "token_id": token_id,
            "scopes": ["evaluation:read", "evidence:read"],
            "expires_at": null,
        })
    );
    assert_eq!(
        member_names(&collected.body),
        [
            "access_token",
            "token_type",
            "token_id",
            "scopes",
            "expires_at"
        ]
    );
    assert!(access_token.starts_with("jcli_"), "{access_token}");
    assert_eq!(access_token.len(), 69);

    // It is handed over once: collecting deleted the sign-in.
    assert_not_collected(&collect(&router, device_code).await, EXPIRED);
    assert!(stored_device_codes(&app).await.is_empty());

    // The token authenticates token-protected routes, with the scopes that
    // were asked for and no others.
    let bearer = format!("Bearer {access_token}");
    let datasets = "/api/v1/evaluation/datasets";
    let read = send(
        &router,
        with_authorization(Method::GET, datasets, &bearer, None),
    )
    .await;
    assert_eq!(read.status, StatusCode::OK, "{}", read.body);
    let write = send(
        &router,
        with_authorization(Method::POST, datasets, &bearer, Some(json!({}))),
    )
    .await;
    assert_eq!(write.status, StatusCode::FORBIDDEN, "{}", write.body);
    assert_eq!(write.body["missing_scopes"], json!(["evaluation:write"]));

    // It is an ordinary token of the person who approved: listed with the
    // client name, the requested scopes, and no expiry.
    let users = send(&router, get("/api/v1/users", Some(&cookie))).await;
    let tokens = listed_tokens(&router, &cookie).await;
    assert_eq!(
        tokens,
        [json!({
            "id": token_id,
            "name": CLIENT_NAME,
            "token": access_token,
            "scopes": ["evaluation:read", "evidence:read"],
            "expires_at": null,
            "created_by_user_id": users.body[0]["id"],
            "created_at": tokens[0]["created_at"],
        })]
    );
}

#[tokio::test]
async fn the_minted_token_belongs_to_the_user_who_approved() {
    let (router, _app) = app();
    let owner = sign_up(&router).await;
    let created = send(
        &router,
        post(
            "/api/v1/users",
            Some(&owner),
            json!({"email": "second@example.com", "password": PASSWORD}),
        ),
    )
    .await;
    assert_eq!(created.status, StatusCode::OK, "{}", created.body);
    let signed_in = send(
        &router,
        post(
            "/api/v1/sign-in",
            None,
            json!({"email": "second@example.com", "password": PASSWORD}),
        ),
    )
    .await;
    let second = session_cookie(&signed_in);

    let started = start(&router, &["evaluation:write"]).await;
    let approved = approve(&router, &second, text(&started, "user_code")).await;
    assert_eq!(approved.status, StatusCode::OK, "{}", approved.body);

    let users = send(&router, get("/api/v1/users", Some(&owner))).await;
    assert_eq!(users.body[1]["email"], "second@example.com");
    let tokens = listed_tokens(&router, &owner).await;
    assert_eq!(tokens.len(), 1);
    assert_eq!(tokens[0]["created_by_user_id"], users.body[1]["id"]);
}

#[tokio::test]
async fn a_denied_sign_in_tells_the_cli_once_and_mints_nothing() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let started = start(&router, &["evaluation:read"]).await;
    let device_code = text(&started, "device_code");
    let user_code = text(&started, "user_code");

    let denied = deny(&router, &cookie, user_code).await;
    assert_eq!(denied.status, StatusCode::OK, "{}", denied.body);
    assert_eq!(denied.body, json!({"message": "CLI sign-in denied"}));

    // A denied sign-in is decided. It cannot be approved after all.
    assert_not_found(&page(&router, &cookie, user_code).await);
    assert_not_found(&approve(&router, &cookie, user_code).await);
    assert_not_found(&deny(&router, &cookie, user_code).await);

    // The terminal is told once. That deletes the sign-in.
    assert_not_collected(&collect(&router, device_code).await, DENIED);
    assert!(stored_device_codes(&app).await.is_empty());
    assert_not_collected(&collect(&router, device_code).await, EXPIRED);

    assert!(listed_tokens(&router, &cookie).await.is_empty());
}

#[tokio::test]
async fn a_poll_before_the_decision_keeps_answering_pending() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let started = start(&router, &["evaluation:read"]).await;
    let device_code = text(&started, "device_code");

    for _ in 0..3 {
        assert_not_collected(&collect(&router, device_code).await, PENDING);
    }

    // Polling changed nothing: the sign-in is still there to be approved.
    assert_eq!(stored_device_codes(&app).await, [device_code]);
    let approved = approve(&router, &cookie, text(&started, "user_code")).await;
    assert_eq!(approved.status, StatusCode::OK, "{}", approved.body);
    assert_eq!(collect(&router, device_code).await.status, StatusCode::OK);
}

#[tokio::test]
async fn an_unknown_code_is_refused() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    // A sign-in exists, so a miss is a miss on the code.
    start(&router, &["evaluation:read"]).await;

    let unknown_device_code = format!("jdev_{}", "a".repeat(64));
    assert_not_collected(&collect(&router, &unknown_device_code).await, EXPIRED);

    assert_not_found(&page(&router, &cookie, "BCDF-GHJK").await);
    assert_not_found(&approve(&router, &cookie, "BCDF-GHJK").await);
    assert_not_found(&deny(&router, &cookie, "BCDF-GHJK").await);
    assert!(listed_tokens(&router, &cookie).await.is_empty());
}

#[tokio::test]
async fn text_that_is_not_a_code_is_a_caller_validation_error() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;

    for body in [
        json!({"device_code": "jdev_too-short"}),
        json!({"device_code": format!("jcli_{}", "a".repeat(64))}),
        json!({"device_code": format!("jdev_{}", "+".repeat(64))}),
        json!({"device_code": ""}),
        json!({"device_code": 7}),
        json!({"device_code": format!("jdev_{}", "a".repeat(64)), "extra": true}),
        json!({}),
    ] {
        let reply = send(&router, post(COLLECT, None, body.clone())).await;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
        assert_eq!(reply.body["code"], "invalid_request", "{body}");
    }
    let malformed = collect(&router, "jdev_too-short").await;
    assert_eq!(
        malformed.body,
        json!({
            "code": "invalid_request",
            "message": "device_code: device_code must be jdev_ followed by 64 URL-safe characters",
        })
    );

    // Seven letters, nine letters, a misplaced hyphen, two hyphens, another
    // separator, vowels, and digits.
    for user_code in [
        "WDJB-MJH",
        "WDJBMJHTT",
        "WDJ-BMJHT",
        "WDJB--MJHT",
        "WDJB_MJHT",
        "AEIO-UAEI",
        "1234-5678",
    ] {
        for reply in [
            page(&router, &cookie, user_code).await,
            approve(&router, &cookie, user_code).await,
            deny(&router, &cookie, user_code).await,
        ] {
            assert_eq!(
                reply.status,
                StatusCode::UNPROCESSABLE_ENTITY,
                "{user_code}"
            );
            assert_eq!(
                reply.body,
                json!({
                    "code": "invalid_request",
                    "message": "Invalid URL: user_code must be eight letters in two groups of four, such as WDJB-MJHT",
                }),
                "{user_code}"
            );
        }
    }
}

#[test]
fn a_user_code_is_held_as_stored_and_shown_with_its_hyphen() {
    for typed in [
        "WDJB-MJHT",
        "WDJBMJHT",
        "wdjb-mjht",
        "wdjbmjht",
        "Wdjb-mJht",
    ] {
        let user_code = UserCode::try_from(typed.to_string()).unwrap();
        assert_eq!(user_code.0, "WDJBMJHT", "{typed}");
        assert_eq!(user_code.shown(), "WDJB-MJHT", "{typed}");
    }
    assert!(UserCode::try_from("WDJB-MJH".to_string()).is_err());
    assert!(DeviceCode::try_from(format!("jdev_{}", "a".repeat(64))).is_ok());
    assert!(DeviceCode::try_from(format!("jdev_{}", "a".repeat(63))).is_err());
}

#[tokio::test]
async fn the_user_code_is_accepted_with_or_without_the_hyphen_in_either_case() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    let started = start(&router, &["evaluation:read"]).await;
    let shown = text(&started, "user_code");
    let bare = shown.replace('-', "");

    let first = page(&router, &cookie, shown).await;
    assert_eq!(first.status, StatusCode::OK, "{}", first.body);
    for typed in [bare.clone(), shown.to_lowercase(), bare.to_lowercase()] {
        let reply = page(&router, &cookie, &typed).await;
        assert_eq!(reply.status, StatusCode::OK, "{typed}: {}", reply.body);
        // However it was typed, it is one sign-in, shown one way.
        assert_eq!(reply.body, first.body, "{typed}");
    }

    let approved = approve(&router, &cookie, &bare.to_lowercase()).await;
    assert_eq!(approved.status, StatusCode::OK, "{}", approved.body);

    let other = start(&router, &["evaluation:read"]).await;
    let denied = deny(
        &router,
        &cookie,
        &text(&other, "user_code").replace('-', ""),
    )
    .await;
    assert_eq!(denied.status, StatusCode::OK, "{}", denied.body);
}

#[tokio::test]
async fn an_expired_sign_in_is_gone() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let long_ago = UtcSeconds::parse("2020-01-01T00:15:00Z").unwrap();

    // Pending when it expired.
    let pending = start(&router, &["evaluation:read"]).await;
    set_expiry(&app, text(&pending, "device_code"), long_ago).await;
    let user_code = text(&pending, "user_code");
    assert_not_found(&page(&router, &cookie, user_code).await);
    assert_not_found(&approve(&router, &cookie, user_code).await);
    assert_not_found(&deny(&router, &cookie, user_code).await);
    assert_not_collected(
        &collect(&router, text(&pending, "device_code")).await,
        EXPIRED,
    );
    assert!(listed_tokens(&router, &cookie).await.is_empty());

    // A sign-in lives until its expiry and not through it.
    let ending = start(&router, &["evaluation:read"]).await;
    set_expiry(&app, text(&ending, "device_code"), UtcSeconds::now()).await;
    assert_not_found(&page(&router, &cookie, text(&ending, "user_code")).await);
    assert_not_collected(
        &collect(&router, text(&ending, "device_code")).await,
        EXPIRED,
    );

    // Denied, and expired before the terminal asked.
    let denied = start(&router, &["evaluation:read"]).await;
    let reply = deny(&router, &cookie, text(&denied, "user_code")).await;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    set_expiry(&app, text(&denied, "device_code"), long_ago).await;
    assert_not_collected(
        &collect(&router, text(&denied, "device_code")).await,
        EXPIRED,
    );

    // Approved, and expired before the terminal collected. The token was
    // minted at approval, so it stays an ordinary token on the tokens page.
    let approved = start(&router, &["evaluation:read"]).await;
    let reply = approve(&router, &cookie, text(&approved, "user_code")).await;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    set_expiry(&app, text(&approved, "device_code"), long_ago).await;
    assert_not_collected(
        &collect(&router, text(&approved, "device_code")).await,
        EXPIRED,
    );
    let tokens = listed_tokens(&router, &cookie).await;
    assert_eq!(tokens.len(), 1);
    assert_eq!(tokens[0]["id"], reply.body["token_id"]);
}

#[tokio::test]
async fn starting_a_sign_in_deletes_the_expired_ones() {
    let (router, app) = app();
    let expired = start(&router, &["evaluation:read"]).await;
    let also_expired = start(&router, &["evaluation:read"]).await;
    let live = start(&router, &["evaluation:read"]).await;
    let long_ago = UtcSeconds::parse("2020-01-01T00:15:00Z").unwrap();
    set_expiry(&app, text(&expired, "device_code"), long_ago).await;
    set_expiry(&app, text(&also_expired, "device_code"), long_ago).await;

    // Nothing runs when a sign-in expires. Its row stays until a start.
    assert_eq!(stored_device_codes(&app).await.len(), 3);

    let started = start(&router, &["evaluation:read"]).await;
    let mut kept = vec![
        text(&live, "device_code").to_string(),
        text(&started, "device_code").to_string(),
    ];
    kept.sort();
    assert_eq!(stored_device_codes(&app).await, kept);
}

#[tokio::test]
async fn a_sign_in_that_draws_a_taken_code_starts_nothing() {
    let (_router, app) = app();
    let sign_in = |device_code: &str, user_code: &str, expires_at: UtcSeconds| NewSignIn {
        device_code: device_code.to_string(),
        user_code: user_code.to_string(),
        client_name: CLIENT_NAME.to_string(),
        scopes: TokenScopes {
            evaluation_read: true,
            evaluation_write: false,
            evidence_read: false,
        },
        created_at: UtcSeconds::now(),
        expires_at,
    };
    let store = |sign_in: NewSignIn| {
        let writer = app.state.application_db.writer.clone();
        async move {
            writer
                .call(move |connection| repo::start(connection, &sign_in))
                .await
        }
    };
    let in_an_hour = UtcSeconds::now().plus_seconds(3600);
    let first = format!("jdev_{}", "a".repeat(64));
    let second = format!("jdev_{}", "b".repeat(64));

    assert!(
        store(sign_in(&first, "WDJBMJHT", in_an_hour))
            .await
            .unwrap()
    );
    // The user code is taken, and then the device code is.
    assert!(
        !store(sign_in(&second, "WDJBMJHT", in_an_hour))
            .await
            .unwrap()
    );
    assert!(
        !store(sign_in(&first, "BCDFGHJK", in_an_hour))
            .await
            .unwrap()
    );
    assert_eq!(stored_device_codes(&app).await, [first.as_str()]);

    // Only a taken code is passed over. A row the schema refuses is an
    // error, not a sign-in that quietly did not start.
    assert!(
        store(sign_in(&second, "wdjb-mjht", in_an_hour))
            .await
            .is_err()
    );

    // The codes of an expired sign-in are free again.
    set_expiry(&app, &first, UtcSeconds::now()).await;
    assert!(
        store(sign_in(&second, "WDJBMJHT", in_an_hour))
            .await
            .unwrap()
    );
    assert_eq!(stored_device_codes(&app).await, [second.as_str()]);
}

#[tokio::test]
async fn the_approval_page_needs_a_session_and_a_token_is_not_one() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    let token = send(
        &router,
        post(
            TOKENS,
            Some(&cookie),
            json!({
                "name": "Every scope",
                "scopes": ["evaluation:read", "evaluation:write", "evidence:read"],
            }),
        ),
    )
    .await;
    assert_eq!(token.status, StatusCode::CREATED, "{}", token.body);
    let bearer = format!("Bearer {}", text(&token.body, "token"));
    let started = start(&router, &["evaluation:read"]).await;
    let user_code = text(&started, "user_code");

    let no_session = json!({"code": "unauthorized", "message": "No valid session"});
    for (method, uri) in [
        (Method::GET, format!("{SIGN_INS}/{user_code}")),
        (Method::POST, format!("{SIGN_INS}/{user_code}/approve")),
        (Method::POST, format!("{SIGN_INS}/{user_code}/deny")),
    ] {
        let anonymous = send(&router, request(method.clone(), &uri, None, None)).await;
        assert_eq!(anonymous.status, StatusCode::UNAUTHORIZED, "{method} {uri}");
        assert_eq!(anonymous.body, no_session, "{method} {uri}");

        let with_token = send(
            &router,
            with_authorization(method.clone(), &uri, &bearer, None),
        )
        .await;
        assert_eq!(
            with_token.status,
            StatusCode::UNAUTHORIZED,
            "{method} {uri}"
        );
        assert_eq!(with_token.body, no_session, "{method} {uri}");
    }

    // Nothing was decided, and only the one token exists.
    assert_not_collected(
        &collect(&router, text(&started, "device_code")).await,
        PENDING,
    );
    assert_eq!(listed_tokens(&router, &cookie).await.len(), 1);
}

#[tokio::test]
async fn an_invalid_start_request_is_refused() {
    let (router, app) = app();

    for body in [
        json!({"client_name": "", "scopes": ["evaluation:read"]}),
        json!({"client_name": "   ", "scopes": ["evaluation:read"]}),
        json!({"client_name": " padded ", "scopes": ["evaluation:read"]}),
        json!({"client_name": "é".repeat(129), "scopes": ["evaluation:read"]}),
        json!({"client_name": 7, "scopes": ["evaluation:read"]}),
        json!({"client_name": CLIENT_NAME, "scopes": []}),
        json!({"client_name": CLIENT_NAME, "scopes": ["evaluation:read", "evaluation:read"]}),
        json!({"client_name": CLIENT_NAME, "scopes": ["evaluation:admin"]}),
        json!({"client_name": CLIENT_NAME, "scopes": "evaluation:read"}),
        json!({"client_name": CLIENT_NAME, "scopes": ["evaluation:read"], "expires_at": null}),
        json!({"client_name": CLIENT_NAME}),
        json!({"scopes": ["evaluation:read"]}),
    ] {
        let reply = send(&router, post(SIGN_INS, None, body.clone())).await;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
        assert_eq!(reply.body["code"], "invalid_request", "{body}");
    }
    // The message names the member and the reason, as a token name's does.
    for (body, message) in [
        (
            json!({"client_name": "", "scopes": ["evaluation:read"]}),
            "client_name: name must not be blank",
        ),
        (
            json!({"client_name": "é".repeat(129), "scopes": ["evaluation:read"]}),
            "client_name: name must be at most 256 UTF-8 bytes",
        ),
        (
            json!({"client_name": CLIENT_NAME, "scopes": []}),
            "scopes: scopes must contain at least one scope",
        ),
        (
            json!({"client_name": CLIENT_NAME, "scopes": ["evaluation:read", "evaluation:read"]}),
            "scopes: scopes must not contain duplicates",
        ),
    ] {
        let reply = send(&router, post(SIGN_INS, None, body.clone())).await;
        assert_eq!(
            reply.body,
            json!({"code": "invalid_request", "message": message}),
            "{body}"
        );
    }
    assert!(stored_device_codes(&app).await.is_empty());

    // 256 bytes is the longest name, and every scope may be asked for.
    let longest = send(
        &router,
        post(
            SIGN_INS,
            None,
            json!({
                "client_name": "é".repeat(128),
                "scopes": ["evidence:read", "evaluation:write", "evaluation:read"],
            }),
        ),
    )
    .await;
    assert_eq!(longest.status, StatusCode::CREATED, "{}", longest.body);
}

#[tokio::test]
async fn deleting_the_minted_token_before_it_is_collected_ends_the_sign_in() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let started = start(&router, &["evaluation:read"]).await;
    let approved = approve(&router, &cookie, text(&started, "user_code")).await;
    assert_eq!(approved.status, StatusCode::OK, "{}", approved.body);

    // The person thinks again and deletes the token on the tokens page.
    let uri = format!("{TOKENS}/{}", text(&approved.body, "token_id"));
    let deleted = send(&router, delete(&uri, Some(&cookie))).await;
    assert_eq!(deleted.status, StatusCode::NO_CONTENT);

    // The sign-in went with its token: there is nothing left to collect.
    assert!(stored_device_codes(&app).await.is_empty());
    assert_not_collected(
        &collect(&router, text(&started, "device_code")).await,
        EXPIRED,
    );
}

#[tokio::test]
async fn concurrent_polls_collect_the_token_once() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    let started = start(&router, &["evaluation:read"]).await;
    let approved = approve(&router, &cookie, text(&started, "user_code")).await;
    assert_eq!(approved.status, StatusCode::OK, "{}", approved.body);

    let polls = (0..10)
        .map(|_| {
            post(
                COLLECT,
                None,
                json!({"device_code": text(&started, "device_code")}),
            )
        })
        .collect();
    let replies = send_all(&router, polls).await;
    let collected: Vec<&Reply> = replies
        .iter()
        .filter(|reply| reply.status == StatusCode::OK)
        .collect();
    assert_eq!(collected.len(), 1);
    assert_eq!(collected[0].body["token_id"], approved.body["token_id"]);
    for refused in replies
        .iter()
        .filter(|reply| reply.status != StatusCode::OK)
    {
        assert_not_collected(refused, EXPIRED);
    }
}

#[tokio::test]
async fn concurrent_approvals_mint_one_token() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    let started = start(&router, &["evaluation:read"]).await;
    let user_code = text(&started, "user_code");

    let approvals = (0..10)
        .map(|_| decision(user_code, "approve", Some(&cookie)))
        .collect();
    let replies = send_all(&router, approvals).await;
    let approved: Vec<&Reply> = replies
        .iter()
        .filter(|reply| reply.status == StatusCode::OK)
        .collect();
    assert_eq!(approved.len(), 1);
    for refused in replies
        .iter()
        .filter(|reply| reply.status != StatusCode::OK)
    {
        assert_not_found(refused);
    }

    let tokens = listed_tokens(&router, &cookie).await;
    assert_eq!(tokens.len(), 1);
    assert_eq!(tokens[0]["id"], approved[0].body["token_id"]);
}

#[test]
fn the_published_document_names_the_contract() {
    let document = crate::openapi::published(&crate::app::openapi()).unwrap();
    let reference = |name: &str| json!({"$ref": format!("#/components/schemas/{name}")});
    let operations = [
        (
            "/api/v1/cli-sign-ins",
            "post",
            "start_cli_sign_in",
            Some("CliSignInStart"),
            ("201", "CliSignInStarted"),
        ),
        (
            "/api/v1/cli-sign-ins/token",
            "post",
            "collect_cli_sign_in_token",
            Some("CliSignInTokenRequest"),
            ("200", "CliSignInToken"),
        ),
        (
            "/api/v1/cli-sign-ins/{user_code}",
            "get",
            "get_cli_sign_in",
            None,
            ("200", "CliSignInRead"),
        ),
        (
            "/api/v1/cli-sign-ins/{user_code}/approve",
            "post",
            "approve_cli_sign_in",
            None,
            ("200", "CliSignInApproved"),
        ),
        (
            "/api/v1/cli-sign-ins/{user_code}/deny",
            "post",
            "deny_cli_sign_in",
            None,
            ("200", "UserResponse"),
        ),
    ];
    for (path, method, operation_id, request_body, (status, response)) in operations {
        let operation = &document["paths"][path][method];
        assert_eq!(operation["operationId"], operation_id, "{method} {path}");
        // A session or a device code is the credential, never a token.
        assert_eq!(operation["security"], Value::Null, "{method} {path}");
        match request_body {
            Some(name) => assert_eq!(
                operation["requestBody"]["content"]["application/json"]["schema"],
                reference(name),
                "{method} {path}"
            ),
            None => assert_eq!(operation["requestBody"], Value::Null, "{method} {path}"),
        }
        assert_eq!(
            operation["responses"][status]["content"]["application/json"]["schema"],
            reference(response),
            "{method} {path}"
        );
    }
    // Every refusal of a poll is the one error body.
    assert_eq!(
        document["paths"]["/api/v1/cli-sign-ins/token"]["post"]["responses"]["400"]["content"]["application/json"]
            ["schema"],
        reference("ErrorResponse")
    );

    let schemas = &document["components"]["schemas"];
    for (name, members) in [
        ("CliSignInStart", json!(["client_name", "scopes"])),
        (
            "CliSignInStarted",
            json!([
                "device_code",
                "user_code",
                "verification_path",
                "expires_in",
                "interval"
            ]),
        ),
        ("CliSignInTokenRequest", json!(["device_code"])),
        (
            "CliSignInToken",
            json!([
                "access_token",
                "token_type",
                "token_id",
                "scopes",
                "expires_at"
            ]),
        ),
        (
            "CliSignInRead",
            json!(["user_code", "client_name", "scopes", "expires_at"]),
        ),
        ("CliSignInApproved", json!(["token_id", "token_name"])),
    ] {
        assert_eq!(schemas[name]["required"], members, "{name}");
        assert_eq!(
            schemas[name]["properties"].as_object().unwrap().len(),
            members.as_array().unwrap().len(),
            "{name}"
        );
        assert_eq!(schemas[name]["additionalProperties"], false, "{name}");
    }
    // The scopes are the developer token scopes, counted as token creation
    // counts them.
    for member in ["items", "minItems", "maxItems"] {
        assert_eq!(
            schemas["CliSignInStart"]["properties"]["scopes"][member],
            schemas["EvaluationTokenCreate"]["properties"]["scopes"][member],
            "{member}"
        );
    }
    assert_eq!(
        schemas["CliSignInStart"]["properties"]["scopes"]["items"],
        reference("EvaluationTokenScope")
    );
    assert_eq!(
        schemas["CliSignInToken"]["properties"]["token_type"]["const"],
        "bearer"
    );
}
