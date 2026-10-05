//! Application Telemetry API key management through the router.

use std::collections::HashSet;

use axum::Router;
use axum::http::{Method, StatusCode};
use serde_json::json;
use tokio::task::JoinSet;

use crate::test_http::{Reply, app, delete, get, post, request, send, sign_up};

const KEYS: &str = "/api/v1/api-keys";

#[tokio::test]
async fn api_keys_are_created_listed_and_deleted() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;

    let created = send(
        &router,
        post(
            "/api/v1/api-keys",
            Some(&cookie),
            json!({"name": "Production"}),
        ),
    )
    .await;
    assert_eq!(created.status, StatusCode::CREATED);
    let id = created.body["id"].as_str().unwrap().to_string();
    let key = created.body["key"].as_str().unwrap();
    assert_eq!(id.len(), 22);
    assert!(key.starts_with("jtel_") && key.len() == 69, "{key}");
    assert_eq!(created.body["name"], "Production");
    let created_at = created.body["created_at"].as_str().unwrap();
    assert!(
        created_at.ends_with('Z') && created_at.len() == 20,
        "{created_at}"
    );

    let empty_name = send(
        &router,
        post("/api/v1/api-keys", Some(&cookie), json!({"name": "   "})),
    )
    .await;
    assert_eq!(empty_name.status, StatusCode::UNPROCESSABLE_ENTITY);
    assert!(
        empty_name.body["message"]
            .as_str()
            .unwrap()
            .contains("API key name cannot be empty")
    );

    let listed = send(&router, get("/api/v1/api-keys", Some(&cookie))).await;
    assert_eq!(listed.status, StatusCode::OK);
    assert_eq!(listed.body, json!([created.body]));

    let uri = format!("/api/v1/api-keys/{id}");
    let deleted = send(&router, request(Method::DELETE, &uri, Some(&cookie), None)).await;
    assert_eq!(deleted.status, StatusCode::NO_CONTENT);
    let again = send(&router, request(Method::DELETE, &uri, Some(&cookie), None)).await;
    assert_eq!(again.status, StatusCode::NOT_FOUND);
    assert_eq!(
        again.body,
        json!({"code": "not_found", "message": "API key not found"})
    );

    // An identifier that is not UTF-8 gets the standard body too.
    let unreadable = send(&router, delete("/api/v1/api-keys/%FF", Some(&cookie))).await;
    assert_eq!(unreadable.status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(unreadable.body["code"], "invalid_request");
}

/// Send every request at once and collect the replies.
async fn send_all(
    router: &Router,
    requests: Vec<axum::http::Request<axum::body::Body>>,
) -> Vec<Reply> {
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
async fn concurrent_creates_all_succeed_with_distinct_keys() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;

    let creates = (0..20)
        .map(|number| {
            post(
                KEYS,
                Some(&cookie),
                json!({"name": format!("Key {number}")}),
            )
        })
        .collect();
    let created = send_all(&router, creates).await;
    assert!(
        created
            .iter()
            .all(|reply| reply.status == StatusCode::CREATED)
    );
    let ids: HashSet<&str> = created
        .iter()
        .map(|reply| reply.body["id"].as_str().unwrap())
        .collect();
    let keys: HashSet<&str> = created
        .iter()
        .map(|reply| reply.body["key"].as_str().unwrap())
        .collect();
    assert_eq!(ids.len(), 20);
    assert_eq!(keys.len(), 20);

    let listed = send(&router, get(KEYS, Some(&cookie))).await;
    assert_eq!(listed.body.as_array().unwrap().len(), 20);
}

#[tokio::test]
async fn a_listing_made_while_keys_are_created_is_always_whole() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;

    let mut requests = Vec::new();
    for number in 0..20 {
        requests.push(post(
            KEYS,
            Some(&cookie),
            json!({"name": format!("Key {number}")}),
        ));
        requests.push(get(KEYS, Some(&cookie)));
    }
    for reply in send_all(&router, requests).await {
        match reply.status {
            StatusCode::CREATED => {}
            StatusCode::OK => {
                let listed = reply.body.as_array().unwrap();
                assert!(listed.len() <= 20);
                // Every listed key is a complete, committed record.
                for key in listed {
                    assert!(key["key"].as_str().unwrap().starts_with("jtel_"));
                    assert!(key["name"].as_str().unwrap().starts_with("Key "));
                }
            }
            other => panic!("unexpected status {other}: {}", reply.body),
        }
    }
}

#[tokio::test]
async fn concurrent_deletes_of_one_key_delete_it_once() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    let created = send(
        &router,
        post(KEYS, Some(&cookie), json!({"name": "Delete me"})),
    )
    .await;
    let uri = format!("{KEYS}/{}", created.body["id"].as_str().unwrap());

    let deletes = (0..10).map(|_| delete(&uri, Some(&cookie))).collect();
    let replies = send_all(&router, deletes).await;
    let deleted = replies
        .iter()
        .filter(|reply| reply.status == StatusCode::NO_CONTENT)
        .count();
    let not_found = replies
        .iter()
        .filter(|reply| reply.status == StatusCode::NOT_FOUND)
        .count();
    assert_eq!((deleted, not_found), (1, 9));

    let listed = send(&router, get(KEYS, Some(&cookie))).await;
    assert_eq!(listed.body, json!([]));
}

#[tokio::test]
async fn a_database_failure_is_a_500_with_the_standard_body_and_passes() {
    let (router, app) = app();
    let cookie = sign_up(&router).await;
    let created = send(&router, post(KEYS, Some(&cookie), json!({"name": "Kept"}))).await;
    let rename = |statement: &'static str| {
        let writer = app.state.application_db.writer.clone();
        async move {
            writer
                .call(move |connection| connection.execute_batch(statement))
                .await
                .unwrap();
        }
    };
    let internal_error = json!({"code": "internal_error", "message": "Internal server error"});

    // The table every key statement names is gone.
    rename("ALTER TABLE api_keys RENAME TO api_keys_away").await;
    let uri = format!("{KEYS}/{}", created.body["id"].as_str().unwrap());
    for failing in [
        get(KEYS, Some(&cookie)),
        post(KEYS, Some(&cookie), json!({"name": "Lost"})),
        delete(&uri, Some(&cookie)),
    ] {
        let reply = send(&router, failing).await;
        assert_eq!(reply.status, StatusCode::INTERNAL_SERVER_ERROR);
        // Nothing about the database reaches the caller.
        assert_eq!(reply.body, internal_error);
    }

    // The failure leaves nothing behind: the same connections work again.
    rename("ALTER TABLE api_keys_away RENAME TO api_keys").await;
    let listed = send(&router, get(KEYS, Some(&cookie))).await;
    assert_eq!(listed.status, StatusCode::OK);
    assert_eq!(listed.body, json!([created.body]));
}
