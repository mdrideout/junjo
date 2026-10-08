//! Junjo AI Studio backend.
//!
//! One process serving the HTTP API and the internal gRPC service, with a
//! dedicated metadata indexer thread. See Studio ADR-011.

use std::net::SocketAddr;
use std::process::ExitCode;
use std::sync::Arc;

use anyhow::Context;
use tokio::net::TcpListener;
use tokio_util::sync::CancellationToken;
use tonic::transport::Server;
use tonic::transport::server::TcpIncoming;

mod app;
mod config;
#[cfg(test)]
mod cross_service_tests;
mod db;
mod error;
mod features;
mod ids;
mod logging;
mod openapi;
mod pagination;
mod proto;
mod state;
#[cfg(test)]
mod test_http;
#[cfg(test)]
mod test_support;
mod text;
mod timestamps;
mod ui;

use config::Config;
use features::auth::session_store::SqliteSessionStore;
use features::config::ConfigResponse;
use features::internal_auth::InternalAuth;
use features::otel_spans::query::QueryEngine;
use features::parquet_indexer::{Indexer, IndexerSettings};
use features::span_ingestion::IngestionClient;
use proto::internal_auth_service_server::InternalAuthServiceServer;
use state::AppState;
use ui::Ui;

fn main() -> ExitCode {
    // `junjo-backend openapi` prints the OpenAPI document and exits. It needs
    // no configuration, so the document can be exported anywhere.
    if std::env::args().nth(1).as_deref() == Some("openapi") {
        return print_openapi();
    }

    let config = match Config::from_env() {
        Ok(config) => config,
        Err(error) => {
            eprintln!("Configuration error: {error}");
            return ExitCode::from(2);
        }
    };
    logging::init(&config);

    let runtime = match tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
    {
        Ok(runtime) => runtime,
        Err(error) => {
            tracing::error!(%error, "failed to start the async runtime");
            return ExitCode::FAILURE;
        }
    };
    match runtime.block_on(run(config, shutdown_signal())) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            tracing::error!(
                error = format!("{error:#}"),
                "backend stopped with an error"
            );
            ExitCode::FAILURE
        }
    }
}

fn print_openapi() -> ExitCode {
    let rendered = openapi::published(&app::openapi())
        .and_then(|document| serde_json::to_string_pretty(&document));
    match rendered {
        Ok(document) => {
            println!("{document}");
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("Failed to render the OpenAPI document: {error}");
            ExitCode::FAILURE
        }
    }
}

/// Run the backend until `stop_requested` resolves, or until a long-lived
/// task ends by itself, which is an error. `stop_requested` yields the name
/// of what asked.
async fn run(
    config: Config,
    stop_requested: impl Future<Output = &'static str>,
) -> anyhow::Result<()> {
    tracing::info!(
        version = env!("CARGO_PKG_VERSION"),
        environment = ?config.environment,
        http_port = config.http_port,
        grpc_port = config.grpc_port,
        sqlite_path = %config.sqlite_path.display(),
        metadata_db_path = %config.metadata_db_path.display(),
        parquet_storage_path = %config.parquet_storage_path.display(),
        ingestion = %format_args!("{}:{}", config.ingestion_host, config.ingestion_port),
        "starting Junjo AI Studio backend"
    );

    // Bind both listeners before doing anything else, so a port conflict
    // stops the process instead of leaving one listener missing.
    let http_listener = bind(config.http_port).await?;
    let grpc_listener = bind(config.grpc_port).await?;

    let ui = config
        .ui_dir
        .as_deref()
        .map(Ui::open)
        .transpose()?
        .map(Arc::new);
    match &config.ui_dir {
        Some(directory) => tracing::info!(directory = %directory.display(), "serving the UI"),
        None => tracing::info!("JUNJO_UI_DIR is not set: serving the API only"),
    }

    let application_db = db::open_application_db(&config.sqlite_path)?;
    let metadata = db::open_metadata_db(&config.metadata_db_path)?;

    let query = Arc::new(QueryEngine::new(&config.datafusion)?);

    let mut indexer = Indexer::spawn(
        IndexerSettings {
            parquet_storage_path: std::path::absolute(&config.parquet_storage_path)?,
            poll_interval: config.indexer_poll_interval,
            batch_size: config.indexer_batch_size,
            read_batch_rows: config.datafusion.batch_size,
        },
        metadata.writer,
    )
    .context("failed to start the parquet indexer thread")?;
    let stop_indexer = indexer.shutdown_sender();

    let state = AppState {
        application_db: application_db.clone(),
        metadata: metadata.reader,
        session_store: SqliteSessionStore::new(application_db.clone()),
        ingestion: IngestionClient::new(
            &config.ingestion_host,
            config.ingestion_port,
            &config.internal_grpc_token,
        )?,
        query,
        indexer: indexer.handle(),
        deployment: Arc::new(ConfigResponse {
            environment: config.environment.as_str(),
            otlp_endpoint: config.otlp_endpoint(),
        }),
        ui,
    };

    let shutdown = CancellationToken::new();
    let mut http_server = tokio::spawn({
        let router = app::router(state, config.is_production());
        let shutdown = shutdown.clone();
        async move {
            axum::serve(http_listener, router)
                .with_graceful_shutdown(shutdown.cancelled_owned())
                .await
        }
    });
    let mut grpc_server = tokio::spawn({
        let service = InternalAuthServiceServer::new(InternalAuth::new(
            application_db.reader.clone(),
            config.internal_grpc_token.clone(),
        ));
        let shutdown = shutdown.clone();
        async move {
            Server::builder()
                .add_service(service)
                .serve_with_incoming_shutdown(
                    TcpIncoming::from(grpc_listener),
                    shutdown.cancelled_owned(),
                )
                .await
        }
    });
    tracing::info!("HTTP and internal gRPC servers started");

    // Run until asked to stop, or until a long-lived task ends by itself.
    let stopped_early = tokio::select! {
        signal = stop_requested => {
            tracing::info!(signal, "shutdown signal received");
            None
        }
        ended = &mut http_server => Some(("HTTP server", how_it_ended(ended))),
        ended = &mut grpc_server => Some(("internal gRPC server", how_it_ended(ended))),
        ended = &mut indexer.finished => Some((
            "parquet indexer",
            match ended {
                Ok(()) => "it returned".to_string(),
                Err(_) => "its thread panicked".to_string(),
            },
        )),
    };
    let stopped_task = stopped_early.as_ref().map(|(task, _)| *task);

    shutdown.cancel();
    stop_indexer();
    if stopped_task != Some("HTTP server") {
        http_server.await??;
    }
    if stopped_task != Some("internal gRPC server") {
        grpc_server.await??;
    }
    if stopped_task != Some("parquet indexer") && indexer.finished.await.is_err() {
        tracing::error!("parquet indexer thread panicked");
    }
    // The indexer checkpoints the metadata index as it stops.
    application_db
        .writer
        .call(|connection| db::checkpoint(connection))
        .await?;
    tracing::info!("SQLite WAL checkpointed");

    match stopped_early {
        None => Ok(()),
        Some((task, cause)) => anyhow::bail!("{task} terminated unexpectedly: {cause}"),
    }
}

/// Why a long-lived task ended, for the error that stops the process.
fn how_it_ended<E: std::fmt::Display>(
    ended: Result<Result<(), E>, tokio::task::JoinError>,
) -> String {
    match ended {
        Ok(Ok(())) => "it returned".to_string(),
        Ok(Err(error)) => error.to_string(),
        Err(error) => error.to_string(),
    }
}

async fn bind(port: u16) -> anyhow::Result<TcpListener> {
    let address = SocketAddr::from(([0, 0, 0, 0], port));
    TcpListener::bind(address)
        .await
        .with_context(|| format!("unable to bind {address}"))
}

async fn shutdown_signal() -> &'static str {
    use tokio::signal::unix::{SignalKind, signal};

    let mut terminate = signal(SignalKind::terminate()).expect("install SIGTERM handler");
    let mut interrupt = signal(SignalKind::interrupt()).expect("install SIGINT handler");
    tokio::select! {
        _ = terminate.recv() => "SIGTERM",
        _ = interrupt.recv() => "SIGINT",
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::path::Path;
    use std::time::Duration;

    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpStream;
    use tokio::sync::oneshot;

    use super::*;
    use crate::proto::ValidateApiKeyRequest;
    use crate::proto::internal_auth_service_client::InternalAuthServiceClient;
    use crate::test_support::INTERNAL_TOKEN;

    /// A port nothing is listening on.
    fn free_port() -> u16 {
        std::net::TcpListener::bind("127.0.0.1:0")
            .unwrap()
            .local_addr()
            .unwrap()
            .port()
    }

    fn config(directory: &Path, http_port: u16, grpc_port: u16) -> Config {
        config_with(directory, http_port, grpc_port, &[])
    }

    fn config_with(
        directory: &Path,
        http_port: u16,
        grpc_port: u16,
        more: &[(&'static str, String)],
    ) -> Config {
        let path = |name: &str| directory.join(name).to_str().unwrap().to_string();
        let mut values = HashMap::from([
            ("JUNJO_INTERNAL_GRPC_TOKEN", INTERNAL_TOKEN.to_string()),
            ("PORT", http_port.to_string()),
            ("GRPC_PORT", grpc_port.to_string()),
            ("JUNJO_SQLITE_PATH", path("sqlite/junjo.db")),
            ("JUNJO_METADATA_DB_PATH", path("sqlite/metadata.db")),
            ("JUNJO_PARQUET_STORAGE_PATH", path("parquet")),
            ("JUNJO_DF_SPILL_PATH", path("spill")),
            // Nothing listens here: no ingestion service is part of this test.
            ("INGESTION_HOST", "127.0.0.1".to_string()),
            ("INGESTION_PORT", "9".to_string()),
        ]);
        values.extend(more.iter().cloned());
        Config::from_lookup(|name| values.get(name).cloned()).unwrap()
    }

    /// One HTTP exchange on a fresh connection. Returns the whole response.
    async fn http_get(port: u16, path: &str) -> std::io::Result<String> {
        let mut stream = TcpStream::connect(("127.0.0.1", port)).await?;
        stream
            .write_all(
                format!("GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                    .as_bytes(),
            )
            .await?;
        let mut response = String::new();
        stream.read_to_string(&mut response).await?;
        Ok(response)
    }

    #[tokio::test]
    async fn the_backend_serves_both_listeners_and_stops_when_asked() {
        let directory = tempfile::tempdir().unwrap();
        let (http_port, grpc_port) = (free_port(), free_port());
        let (stop, stopped) = oneshot::channel::<()>();
        let backend = tokio::spawn(run(
            config(directory.path(), http_port, grpc_port),
            async move {
                let _ = stopped.await;
                "test"
            },
        ));

        // Both listeners are bound before anything else starts, so the first
        // connection may arrive before the servers accept; it then waits.
        let mut health = http_get(http_port, "/health").await;
        for _ in 0..200 {
            if health.is_ok() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
            health = http_get(http_port, "/health").await;
        }
        let health = health.unwrap();
        assert!(health.starts_with("HTTP/1.1 200"), "{health}");
        assert!(health.contains(r#""status":"ok""#), "{health}");
        let unknown = http_get(http_port, "/api/v1/unknown").await.unwrap();
        assert!(unknown.starts_with("HTTP/1.1 404"), "{unknown}");

        let mut client =
            InternalAuthServiceClient::connect(format!("http://127.0.0.1:{grpc_port}"))
                .await
                .unwrap();
        let mut request = tonic::Request::new(ValidateApiKeyRequest {
            api_key: "jtel_unknown".to_string(),
        });
        request
            .metadata_mut()
            .insert("x-junjo-internal-token", INTERNAL_TOKEN.parse().unwrap());
        let answer = client.validate_api_key(request).await.unwrap();
        assert!(!answer.into_inner().is_valid);
        drop(client);

        stop.send(()).unwrap();
        backend.await.unwrap().unwrap();

        // Both databases were created, and the application database's log was
        // folded back into it on the way out.
        assert!(directory.path().join("sqlite/junjo.db").is_file());
        assert!(directory.path().join("sqlite/metadata.db").is_file());
        let wal = directory.path().join("sqlite/junjo.db-wal");
        assert!(!wal.exists() || std::fs::metadata(&wal).unwrap().len() == 0);
        assert!(http_get(http_port, "/health").await.is_err());
    }

    #[tokio::test]
    async fn a_configured_ui_is_served_on_the_api_port() {
        let directory = tempfile::tempdir().unwrap();
        let ui = directory.path().join("ui");
        std::fs::create_dir(&ui).unwrap();
        std::fs::write(ui.join("index.html"), "<title>Studio</title>").unwrap();
        let (http_port, grpc_port) = (free_port(), free_port());
        let (stop, stopped) = oneshot::channel::<()>();
        let backend = tokio::spawn(run(
            config_with(
                directory.path(),
                http_port,
                grpc_port,
                &[("JUNJO_UI_DIR", ui.to_str().unwrap().to_string())],
            ),
            async move {
                let _ = stopped.await;
                "test"
            },
        ));

        let mut page = http_get(http_port, "/sign-in").await;
        for _ in 0..200 {
            if page.is_ok() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
            page = http_get(http_port, "/sign-in").await;
        }
        let page = page.unwrap();
        assert!(page.starts_with("HTTP/1.1 200"), "{page}");
        assert!(page.ends_with("<title>Studio</title>"), "{page}");
        // One origin: the API answers on the same port.
        let health = http_get(http_port, "/health").await.unwrap();
        assert!(health.contains(r#""status":"ok""#), "{health}");

        stop.send(()).unwrap();
        backend.await.unwrap().unwrap();
    }

    #[tokio::test]
    async fn a_ui_directory_without_the_app_stops_startup() {
        let directory = tempfile::tempdir().unwrap();
        let error = run(
            config_with(
                directory.path(),
                free_port(),
                free_port(),
                &[(
                    "JUNJO_UI_DIR",
                    directory.path().to_str().unwrap().to_string(),
                )],
            ),
            std::future::pending(),
        )
        .await
        .unwrap_err();
        assert!(
            format!("{error:#}").contains("has no index.html"),
            "{error:#}"
        );
    }

    #[tokio::test]
    async fn a_taken_port_stops_startup_before_anything_is_created() {
        let directory = tempfile::tempdir().unwrap();
        let taken = std::net::TcpListener::bind("0.0.0.0:0").unwrap();
        let taken_port = taken.local_addr().unwrap().port();

        for (http_port, grpc_port) in [(taken_port, free_port()), (free_port(), taken_port)] {
            let error = run(
                config(directory.path(), http_port, grpc_port),
                std::future::pending(),
            )
            .await
            .unwrap_err();
            assert!(
                format!("{error:#}").contains(&format!("unable to bind 0.0.0.0:{taken_port}")),
                "{error:#}"
            );
        }
        assert!(!directory.path().join("sqlite").exists());
    }
}
