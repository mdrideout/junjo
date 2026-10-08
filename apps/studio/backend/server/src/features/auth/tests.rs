//! Sign-in, sign-out, and user management through the router.

use axum::Router;
use axum::http::StatusCode;
use axum::http::header::SET_COOKIE;
use serde_json::{Value, json};

use super::Email;
use crate::test_http::{
    EMAIL, PASSWORD, Reply, app, delete, get, post, send, session_cookie, sign_up,
};

async fn sign_in(router: &Router, cookie: Option<&str>, email: &str, password: &str) -> Reply {
    send(
        router,
        post(
            "/api/v1/sign-in",
            cookie,
            json!({"email": email, "password": password}),
        ),
    )
    .await
}

async fn is_signed_in(router: &Router, cookie: &str) -> bool {
    send(router, get("/api/v1/auth-test", Some(cookie)))
        .await
        .status
        == StatusCode::OK
}

fn invalid_credentials() -> Value {
    json!({"code": "unauthorized", "message": "Invalid credentials"})
}

#[tokio::test]
async fn sign_in_starts_a_session_and_sign_out_ends_only_that_session() {
    let (router, _app) = app();
    let first = sign_up(&router).await;

    // The address is matched in lowercase, as it was stored.
    let signed_in = sign_in(&router, None, " Owner@Example.COM ", PASSWORD).await;
    assert_eq!(signed_in.status, StatusCode::OK, "{}", signed_in.body);
    assert_eq!(signed_in.body, json!({"message": "signed in"}));
    let second = session_cookie(&signed_in);
    assert_ne!(second, first);
    assert!(is_signed_in(&router, &second).await);

    let signed_out = send(&router, post("/api/v1/sign-out", Some(&second), json!({}))).await;
    assert_eq!(signed_out.status, StatusCode::OK);
    assert_eq!(signed_out.body, json!({"message": "signed out"}));
    // The browser is told to drop the cookie.
    let removal = signed_out.headers[SET_COOKIE].to_str().unwrap();
    assert!(removal.starts_with("junjo_session=;"), "{removal}");
    assert!(removal.contains("Max-Age=0"), "{removal}");

    // The ended session is gone from the server; the other session is not.
    assert!(!is_signed_in(&router, &second).await);
    assert!(is_signed_in(&router, &first).await);

    let anonymous = send(&router, post("/api/v1/sign-out", None, json!({}))).await;
    assert_eq!(anonymous.status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn sign_in_rotates_the_session_identifier() {
    let (router, _app) = app();
    let before = sign_up(&router).await;

    let signed_in = sign_in(&router, Some(&before), EMAIL, PASSWORD).await;
    assert_eq!(signed_in.status, StatusCode::OK);
    let after = session_cookie(&signed_in);
    assert_ne!(after, before);
    // An identifier issued before sign-in is never promoted.
    assert!(!is_signed_in(&router, &before).await);
    assert!(is_signed_in(&router, &after).await);
}

#[test]
fn an_email_address_is_a_plain_address_with_a_dotted_domain() {
    for refused in [
        "admin@localhost",
        "Jane <jane@example.com>",
        "jane@[127.0.0.1]",
        "not an address",
    ] {
        assert!(Email::try_from(refused.to_string()).is_err(), "{refused}");
    }
    let accepted = Email::try_from(" Jane@Example.COM ".to_string()).unwrap();
    assert_eq!(accepted.0, "jane@example.com");
}

#[tokio::test]
async fn a_password_at_the_72_byte_bound_is_stored_and_read_in_full() {
    let (router, _app) = app();
    let password = "p".repeat(72);
    let created = send(
        &router,
        post(
            "/api/v1/users/create-first-user",
            None,
            json!({"email": EMAIL, "password": password}),
        ),
    )
    .await;
    assert_eq!(created.status, StatusCode::OK, "{}", created.body);

    assert_eq!(
        sign_in(&router, None, EMAIL, &password).await.status,
        StatusCode::OK
    );
    // The last byte counts.
    let other_last_byte = format!("{}q", "p".repeat(71));
    assert_eq!(
        sign_in(&router, None, EMAIL, &other_last_byte).await.status,
        StatusCode::UNAUTHORIZED
    );
    // A longer password with the same first 72 bytes is not the same password.
    let longer = format!("{password}p");
    assert_eq!(
        sign_in(&router, None, EMAIL, &longer).await.status,
        StatusCode::UNAUTHORIZED
    );
}

#[tokio::test]
async fn refused_credentials_are_one_answer_and_start_no_session() {
    let (router, app) = app();
    sign_up(&router).await;

    for attempt in 0..3 {
        let wrong = sign_in(&router, None, EMAIL, &format!("wrong password {attempt}")).await;
        assert_eq!(wrong.status, StatusCode::UNAUTHORIZED);
        assert_eq!(wrong.body, invalid_credentials());
        assert!(!wrong.headers.contains_key(SET_COOKIE));
    }
    let unknown = sign_in(&router, None, "nobody@example.com", PASSWORD).await;
    assert_eq!(unknown.status, StatusCode::UNAUTHORIZED);
    assert_eq!(unknown.body, invalid_credentials());
    // Longer than any password that could have been stored.
    let too_long = sign_in(&router, None, EMAIL, &"p".repeat(100)).await;
    assert_eq!(too_long.status, StatusCode::UNAUTHORIZED);
    assert_eq!(too_long.body, invalid_credentials());

    // Refusals lock nothing: the right password still works.
    assert_eq!(
        sign_in(&router, None, EMAIL, PASSWORD).await.status,
        StatusCode::OK
    );

    app.state
        .application_db
        .writer
        .call(|connection| connection.execute("UPDATE users SET is_active = 0", []))
        .await
        .unwrap();
    let inactive = sign_in(&router, None, EMAIL, PASSWORD).await;
    assert_eq!(inactive.status, StatusCode::UNAUTHORIZED);
    assert_eq!(inactive.body, invalid_credentials());
}

#[tokio::test]
async fn sql_in_an_email_address_is_only_text() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;

    for payload in [
        "' OR '1'='1",
        "admin'--",
        "'; DROP TABLE users; --",
        "' UNION SELECT * FROM users--",
        "admin' OR '1'='1'--",
        "x'--@example.com",
    ] {
        let reply = sign_in(&router, None, payload, PASSWORD).await;
        assert!(
            reply.status == StatusCode::UNAUTHORIZED
                || reply.status == StatusCode::UNPROCESSABLE_ENTITY,
            "{payload}: {}",
            reply.status
        );
    }
    assert!(is_signed_in(&router, &cookie).await);
}

#[tokio::test]
async fn concurrent_first_user_requests_create_one_user() {
    let (router, _app) = app();
    let attempts = (0..10).map(|number| {
        let router = router.clone();
        async move {
            send(
                &router,
                post(
                    "/api/v1/users/create-first-user",
                    None,
                    json!({"email": format!("user{number}@example.com"), "password": PASSWORD}),
                ),
            )
            .await
        }
    });
    let mut replies = Vec::new();
    let mut tasks = tokio::task::JoinSet::new();
    for attempt in attempts {
        tasks.spawn(attempt);
    }
    while let Some(reply) = tasks.join_next().await {
        replies.push(reply.unwrap());
    }

    let created: Vec<&Reply> = replies
        .iter()
        .filter(|reply| reply.status == StatusCode::OK)
        .collect();
    assert_eq!(created.len(), 1);
    for refused in replies
        .iter()
        .filter(|reply| reply.status != StatusCode::OK)
    {
        assert_eq!(refused.status, StatusCode::BAD_REQUEST);
        assert_eq!(refused.body["code"], "users_already_exist");
    }
    let users = send(
        &router,
        get("/api/v1/users", Some(&session_cookie(created[0]))),
    )
    .await;
    assert_eq!(users.body.as_array().unwrap().len(), 1);
}

#[tokio::test]
async fn users_are_created_listed_and_deleted() {
    let (router, _app) = app();
    let owner = sign_up(&router).await;

    let created = send(
        &router,
        post(
            "/api/v1/users",
            Some(&owner),
            json!({"email": "Second@Example.com", "password": "second password"}),
        ),
    )
    .await;
    assert_eq!(created.status, StatusCode::OK, "{}", created.body);
    assert_eq!(
        created.body,
        json!({"message": "User created successfully"})
    );
    // Creating a user does not sign anyone in.
    assert!(!created.headers.contains_key(SET_COOKIE));

    let duplicate = send(
        &router,
        post(
            "/api/v1/users",
            Some(&owner),
            json!({"email": "second@example.com", "password": "another password"}),
        ),
    )
    .await;
    assert_eq!(duplicate.status, StatusCode::CONFLICT);
    assert_eq!(
        duplicate.body,
        json!({
            "code": "user_email_exists",
            "message": "A user with this email already exists",
        })
    );

    for body in [
        json!({"email": "third@example.com", "password": "short"}),
        json!({"email": "not an address", "password": "long enough"}),
        json!({"email": "third@example.com"}),
    ] {
        let reply = send(&router, post("/api/v1/users", Some(&owner), body.clone())).await;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
    }

    let listed = send(&router, get("/api/v1/users", Some(&owner))).await;
    assert_eq!(listed.status, StatusCode::OK);
    let users = listed.body.as_array().unwrap();
    assert_eq!(
        users
            .iter()
            .map(|user| user["email"].as_str().unwrap())
            .collect::<Vec<_>>(),
        [EMAIL, "second@example.com"]
    );
    for user in users {
        // A password or its hash is never returned.
        assert_eq!(
            user.as_object().unwrap().keys().collect::<Vec<_>>(),
            ["id", "email", "is_active", "created_at", "updated_at"]
        );
        assert_eq!(user["is_active"], true);
    }

    let second = sign_in(&router, None, "second@example.com", "second password").await;
    assert_eq!(second.status, StatusCode::OK);
    let second_cookie = session_cookie(&second);
    assert!(is_signed_in(&router, &second_cookie).await);

    let second_uri = format!("/api/v1/users/{}", users[1]["id"].as_str().unwrap());
    let deleted = send(&router, delete(&second_uri, Some(&owner))).await;
    assert_eq!(deleted.status, StatusCode::OK);
    assert_eq!(
        deleted.body,
        json!({"message": "User deleted successfully"})
    );
    let deleted_again = send(&router, delete(&second_uri, Some(&owner))).await;
    assert_eq!(deleted_again.status, StatusCode::NOT_FOUND);
    assert_eq!(
        deleted_again.body,
        json!({"code": "not_found", "message": "User not found"})
    );

    // The deleted user's session and password stop working.
    assert!(!is_signed_in(&router, &second_cookie).await);
    let refused = sign_in(&router, None, "second@example.com", "second password").await;
    assert_eq!(refused.status, StatusCode::UNAUTHORIZED);
}
