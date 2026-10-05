//! The Studio UI: the built React app, served as static files.
//!
//! The app routes in the browser, so a path that names no file of the build
//! is answered with `index.html`. The build's `.br` and `.gz` siblings are
//! served to a browser that accepts them; nothing is compressed per request.

use std::path::Path;

use axum::body::Body;
use axum::extract::Request;
use axum::http::header::CACHE_CONTROL;
use axum::http::{HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use tower::ServiceExt;
use tower_http::services::{ServeDir, ServeFile};

use crate::error::ApiError;

/// The build puts the files it names by a hash of their content here.
const ASSETS_PREFIX: &str = "/assets/";
/// A hashed file never changes, so a browser keeps it without asking again.
const IMMUTABLE: &str = "public, max-age=31536000, immutable";
/// Every other file is checked with the server before each use. `index.html`
/// names the current hashed files, so a stale copy would load a stale app.
const REVALIDATE: &str = "no-cache";

/// The built UI in one directory.
#[derive(Clone)]
pub struct Ui {
    /// The build's files and nothing else.
    files: ServeDir,
    /// The build's files, and `index.html` for any other path.
    app: ServeDir<ServeFile>,
}

impl Ui {
    /// Serve the build in `directory`. A directory without `index.html` is
    /// an error here, at startup, instead of a failure on every page.
    pub fn open(directory: &Path) -> anyhow::Result<Self> {
        let index = directory.join("index.html");
        anyhow::ensure!(
            index.is_file(),
            "the UI directory {} has no index.html",
            directory.display()
        );
        let files = ServeDir::new(directory)
            .precompressed_br()
            .precompressed_gzip();
        let app = files.clone().fallback(
            ServeFile::new(index)
                .precompressed_br()
                .precompressed_gzip(),
        );
        Ok(Self { files, app })
    }

    /// Answer one GET or HEAD request for a path that is not an API route.
    pub async fn serve(&self, request: Request) -> Response {
        let (response, cache_control) = if request.uri().path().starts_with(ASSETS_PREFIX) {
            let Ok(response) = self.files.clone().oneshot(request).await;
            // A hashed file that is gone stays gone. Answering with the app
            // would have the browser keep HTML under a script's name.
            if response.status() == StatusCode::NOT_FOUND {
                return ApiError::not_found("Not found").into_response();
            }
            (response.map(Body::new), IMMUTABLE)
        } else {
            let Ok(response) = self.app.clone().oneshot(request).await;
            (response.map(Body::new), REVALIDATE)
        };
        let mut response = response;
        if response.status().is_success() || response.status() == StatusCode::NOT_MODIFIED {
            response
                .headers_mut()
                .insert(CACHE_CONTROL, HeaderValue::from_static(cache_control));
        }
        response
    }
}

#[cfg(test)]
mod tests {
    use axum::Router;
    use axum::body::{Body, to_bytes};
    use axum::http::header::{ACCEPT_ENCODING, CONTENT_ENCODING, CONTENT_TYPE, SET_COOKIE, VARY};
    use axum::http::{HeaderMap, Method, Request};
    use serde_json::{Value, json};
    use tower::ServiceExt;

    use super::*;
    use crate::app::router;
    use crate::test_support::{TestApp, test_app};

    const INDEX: &str = "<!doctype html><title>Junjo AI Studio</title>";
    const SCRIPT: &str = "console.log('studio')";

    /// A build: the app, one hashed script with its compressed siblings, and
    /// one file that is not hashed.
    fn build() -> tempfile::TempDir {
        let directory = tempfile::tempdir().unwrap();
        let write = |name: &str, content: &str| {
            let path = directory.path().join(name);
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(path, content).unwrap();
        };
        write("index.html", INDEX);
        write("vite.svg", "<svg/>");
        write("assets/index-1a2b3c.js", SCRIPT);
        // Stand-ins: the service sends a sibling's bytes as they are.
        write("assets/index-1a2b3c.js.br", "brotli bytes");
        write("assets/index-1a2b3c.js.gz", "gzip bytes");
        directory
    }

    /// The application with the build in `directory` as its UI. The
    /// application's databases last as long as the returned value.
    fn studio(directory: &Path) -> (Router, TestApp) {
        let mut app = test_app();
        app.state.ui = Some(std::sync::Arc::new(Ui::open(directory).unwrap()));
        (router(app.state.clone(), false), app)
    }

    struct Served {
        status: StatusCode,
        headers: HeaderMap,
        body: Vec<u8>,
    }

    impl Served {
        fn text(&self) -> &str {
            std::str::from_utf8(&self.body).unwrap()
        }

        fn header(&self, name: impl axum::http::header::AsHeaderName) -> Option<&str> {
            self.headers.get(name).map(|value| value.to_str().unwrap())
        }
    }

    async fn fetch(router: &Router, method: Method, uri: &str, accept_encoding: &str) -> Served {
        let request = Request::builder()
            .method(method)
            .uri(uri)
            .header(ACCEPT_ENCODING, accept_encoding)
            .body(Body::empty())
            .unwrap();
        let response = router.clone().oneshot(request).await.unwrap();
        Served {
            status: response.status(),
            headers: response.headers().clone(),
            body: to_bytes(response.into_body(), usize::MAX)
                .await
                .unwrap()
                .to_vec(),
        }
    }

    async fn get(router: &Router, uri: &str) -> Served {
        fetch(router, Method::GET, uri, "identity").await
    }

    fn not_found() -> Value {
        json!({"code": "not_found", "message": "Not found"})
    }

    #[tokio::test]
    async fn every_page_path_is_the_app_and_is_never_cached() {
        let directory = build();
        let (router, _app) = studio(directory.path());
        for uri in [
            "/",
            "/index.html",
            "/sign-in",
            "/users",
            // A page whose path begins like the API prefix but is not under it.
            "/api-keys",
            "/traces/checkout/0123456789abcdef0123456789abcdef/0123456789abcdef",
            "/workflows/team%2Fcheckout/abc",
        ] {
            let page = get(&router, uri).await;
            assert_eq!(page.status, StatusCode::OK, "{uri}");
            assert_eq!(page.text(), INDEX, "{uri}");
            assert_eq!(page.header(CONTENT_TYPE), Some("text/html"), "{uri}");
            assert_eq!(page.header(CACHE_CONTROL), Some(REVALIDATE), "{uri}");
            // A page never touches the session store.
            assert!(!page.headers.contains_key(SET_COOKIE), "{uri}");
        }
        let head = fetch(&router, Method::HEAD, "/sign-in", "identity").await;
        assert_eq!(head.status, StatusCode::OK);
        assert!(head.body.is_empty());
    }

    #[tokio::test]
    async fn a_hashed_asset_is_cached_for_good_and_another_file_is_revalidated() {
        let directory = build();
        let (router, _app) = studio(directory.path());

        let script = get(&router, "/assets/index-1a2b3c.js").await;
        assert_eq!(script.status, StatusCode::OK);
        assert_eq!(script.text(), SCRIPT);
        assert_eq!(script.header(CONTENT_TYPE), Some("text/javascript"));
        assert_eq!(script.header(CACHE_CONTROL), Some(IMMUTABLE));

        let icon = get(&router, "/vite.svg").await;
        assert_eq!(icon.status, StatusCode::OK);
        assert_eq!(icon.text(), "<svg/>");
        assert_eq!(icon.header(CACHE_CONTROL), Some(REVALIDATE));
    }

    #[tokio::test]
    async fn a_compressed_sibling_is_sent_to_a_browser_that_accepts_it() {
        let directory = build();
        let (router, _app) = studio(directory.path());
        for (accept_encoding, encoding, body) in [
            ("gzip, deflate, br", Some("br"), "brotli bytes"),
            ("gzip", Some("gzip"), "gzip bytes"),
            ("identity", None, SCRIPT),
        ] {
            let script = fetch(
                &router,
                Method::GET,
                "/assets/index-1a2b3c.js",
                accept_encoding,
            )
            .await;
            assert_eq!(script.status, StatusCode::OK, "{accept_encoding}");
            assert_eq!(script.text(), body, "{accept_encoding}");
            assert_eq!(
                script.header(CONTENT_ENCODING),
                encoding,
                "{accept_encoding}"
            );
            // The type is the script's, whichever bytes carry it.
            assert_eq!(script.header(CONTENT_TYPE), Some("text/javascript"));
            // A cache keeps the answers for different browsers apart.
            assert_eq!(script.header(VARY), Some("accept-encoding"));
            assert_eq!(script.header(CACHE_CONTROL), Some(IMMUTABLE));
        }
        // A file with no compressed sibling is sent as it is.
        let page = fetch(&router, Method::GET, "/", "gzip, br").await;
        assert_eq!(page.text(), INDEX);
        assert_eq!(page.header(CONTENT_ENCODING), None);
    }

    #[tokio::test]
    async fn a_missing_asset_is_not_found_and_is_not_the_app() {
        let directory = build();
        let (router, _app) = studio(directory.path());
        for uri in [
            "/assets/index-0ld0ld.js",
            "/assets/",
            "/assets/../index.html",
        ] {
            let missing = get(&router, uri).await;
            assert_eq!(missing.status, StatusCode::NOT_FOUND, "{uri}");
            assert_eq!(
                serde_json::from_slice::<Value>(&missing.body).unwrap(),
                not_found(),
                "{uri}"
            );
            assert_eq!(missing.header(CACHE_CONTROL), None, "{uri}");
        }
    }

    #[tokio::test]
    async fn the_api_and_other_methods_are_never_the_app() {
        let directory = build();
        let (router, _app) = studio(directory.path());
        for (method, uri) in [
            (Method::GET, "/api"),
            (Method::GET, "/api/"),
            (Method::GET, "/api/unknown"),
            (Method::GET, "/api/v1/unknown"),
            (Method::GET, "/api/v2/users"),
            (Method::POST, "/sign-in"),
            (Method::DELETE, "/"),
        ] {
            let reply = fetch(&router, method.clone(), uri, "identity").await;
            assert_eq!(reply.status, StatusCode::NOT_FOUND, "{method} {uri}");
            assert_eq!(
                serde_json::from_slice::<Value>(&reply.body).unwrap(),
                not_found(),
                "{method} {uri}"
            );
        }
        // A real route still answers, with the UI in place.
        let health = get(&router, "/health").await;
        assert_eq!(health.status, StatusCode::OK);
        assert_eq!(health.header(CONTENT_TYPE), Some("application/json"));
        let api = get(&router, "/api/v1/users/db-has-users").await;
        assert_eq!(api.text(), r#"{"users_exist":false}"#);
    }

    #[tokio::test]
    async fn nothing_outside_the_build_is_served() {
        let directory = tempfile::tempdir().unwrap();
        let build = directory.path().join("ui");
        std::fs::create_dir(&build).unwrap();
        std::fs::write(build.join("index.html"), INDEX).unwrap();
        std::fs::write(directory.path().join("secret.txt"), "secret").unwrap();
        let (router, _app) = studio(&build);

        for uri in ["/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"] {
            let reply = get(&router, uri).await;
            assert!(!reply.text().contains("secret"), "{uri}: {}", reply.text());
        }
    }

    #[tokio::test]
    async fn without_a_build_the_process_serves_the_api_only() {
        let app = test_app();
        let router = router(app.state.clone(), false);
        for uri in ["/", "/sign-in", "/assets/index-1a2b3c.js"] {
            let reply = get(&router, uri).await;
            assert_eq!(reply.status, StatusCode::NOT_FOUND, "{uri}");
            assert_eq!(
                serde_json::from_slice::<Value>(&reply.body).unwrap(),
                not_found(),
                "{uri}"
            );
        }
        assert_eq!(get(&router, "/health").await.status, StatusCode::OK);
    }

    #[test]
    fn a_directory_without_the_app_is_refused() {
        let directory = tempfile::tempdir().unwrap();
        let error = Ui::open(directory.path()).err().unwrap().to_string();
        assert!(error.contains("has no index.html"), "{error}");
        assert!(
            error.contains(directory.path().to_str().unwrap()),
            "{error}"
        );
    }
}
