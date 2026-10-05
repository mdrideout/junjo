//! Starts the real ingestion service for one test.
//!
//! `start` gives a test its own ingestion process and a test application
//! wired to it:
//!
//! - the application's ingestion client calls the process's internal API,
//! - the application's cold storage directory is the one the process writes,
//! - the process validates API keys by calling this crate's `InternalAuth`
//!   service, served over the application's database.

use std::fs::File;
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use opentelemetry_proto::tonic::collector::trace::v1::ExportTraceServiceRequest;
use opentelemetry_proto::tonic::collector::trace::v1::trace_service_client::TraceServiceClient;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tonic::Request;
use tonic::metadata::MetadataValue;
use tonic::transport::server::TcpIncoming;
use tonic::transport::{Channel, Endpoint, Server};

use crate::features::api_keys::repo::{self, ApiKey};
use crate::features::internal_auth::InternalAuth;
use crate::features::span_ingestion::IngestionClient;
use crate::proto::internal_auth_service_server::InternalAuthServiceServer;
use crate::test_support::{INTERNAL_TOKEN, TestApp, test_app};
use crate::timestamps::UtcSeconds;

/// The API key every export carries. It exists in the test application's
/// database, which is where ingestion's validation call looks for it.
const API_KEY: &str = "jtel_cross_service_tests";

/// How long a started process may take to accept connections, and how long
/// one export may take. Both normally take milliseconds. The bounds make a
/// process that stalls fail its test instead of hanging the run.
const READY_TIMEOUT: Duration = Duration::from_secs(10);
const EXPORT_TIMEOUT: Duration = Duration::from_secs(30);

/// Held while one test chooses its ports and until its ingestion process has
/// bound them.
///
/// Ingestion binds the port numbers it is given, so its ports are found by
/// binding port zero and releasing it. On a system that hands out free ports
/// at random, a test that starts at the same moment could otherwise be given
/// a port that was just released here.
static STARTING: Mutex<()> = Mutex::const_new(());

/// One running ingestion process. Dropping it kills the process and removes
/// its directory.
pub struct Ingestion {
    process: Child,
    otlp: TraceServiceClient<Channel>,
    internal_port: u16,
    /// Where the process writes cold Parquet files.
    parquet_directory: PathBuf,
    /// Holds the write-ahead log, the cold Parquet files, the hot snapshot,
    /// and the process's log.
    directory: tempfile::TempDir,
}

/// A test application wired to its own ingestion process, which rebuilds the
/// hot snapshot for every request.
pub async fn start() -> (TestApp, Ingestion) {
    start_with_snapshot_reuse(Duration::ZERO).await
}

/// A test application wired to its own ingestion process, which reuses one
/// hot snapshot for `snapshot_reuse`. A deployment reuses one for a second.
pub async fn start_with_snapshot_reuse(snapshot_reuse: Duration) -> (TestApp, Ingestion) {
    let mut app = test_app();
    app.state
        .application_db
        .writer
        .call(|connection| {
            repo::create(
                connection,
                &ApiKey {
                    id: "key-1".to_string(),
                    key: API_KEY.to_string(),
                    name: "cross-service tests".to_string(),
                    created_at: UtcSeconds::now(),
                },
            )
        })
        .await
        .unwrap();

    let binary = ingestion_binary();
    let _starting = STARTING.lock().await;

    // The backend's internal gRPC service, which ingestion calls to validate
    // the key. It stops with the calling test's runtime.
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let backend_port = listener.local_addr().unwrap().port();
    tokio::spawn(
        Server::builder()
            .add_service(InternalAuthServiceServer::new(InternalAuth::new(
                app.state.application_db.reader.clone(),
                INTERNAL_TOKEN.to_string(),
            )))
            .serve_with_incoming(TcpIncoming::from(listener)),
    );

    let ingestion = Ingestion::spawn(binary, backend_port, snapshot_reuse);
    app.state.ingestion =
        IngestionClient::new("127.0.0.1", ingestion.internal_port, INTERNAL_TOKEN).unwrap();
    app.parquet_directory = ingestion.parquet_directory.clone();
    (app, ingestion)
}

impl Ingestion {
    /// Start a process that validates API keys against the backend on
    /// `backend_port`. Returns once the process accepts connections.
    fn spawn(binary: &Path, backend_port: u16, snapshot_reuse: Duration) -> Self {
        let directory = tempfile::tempdir().unwrap();
        let parquet_directory = directory.path().join("parquet");
        let log = File::create(directory.path().join("ingestion.log")).unwrap();
        let (public_port, internal_port) = free_ports();

        // The process gets exactly this environment, so a variable set in the
        // developer's shell cannot change how ingestion behaves in a test.
        let process = Command::new(binary)
            .env_clear()
            .env("WAL_DIR", directory.path().join("wal"))
            .env("PARQUET_OUTPUT_DIR", &parquet_directory)
            .env(
                "SNAPSHOT_PATH",
                directory.path().join("hot_snapshot.parquet"),
            )
            .env("GRPC_PORT", public_port.to_string())
            .env("INTERNAL_GRPC_PORT", internal_port.to_string())
            .env("BACKEND_GRPC_HOST", "127.0.0.1")
            .env("BACKEND_GRPC_PORT", backend_port.to_string())
            .env("JUNJO_INTERNAL_GRPC_TOKEN", INTERNAL_TOKEN)
            // Most tests have a snapshot rebuilt for every request. By
            // default ingestion reuses one for a second, and a test would be
            // answered with a snapshot from before its last export or flush.
            // Without that reuse the next request replaces the snapshot file
            // at once, or removes it when the log is empty, even if an
            // earlier request's caller has not read it yet. A test must
            // therefore not run two queries at once around a flush.
            .env(
                "PREPARE_HOT_SNAPSHOT_CACHE_TTL_MS",
                snapshot_reuse.as_millis().to_string(),
            )
            .env("RUST_LOG", "info")
            .stdin(Stdio::null())
            .stdout(log.try_clone().unwrap())
            .stderr(log)
            .spawn()
            .unwrap_or_else(|error| panic!("cannot start {}: {error}", binary.display()));

        let otlp = Endpoint::from_shared(format!("http://127.0.0.1:{public_port}"))
            .unwrap()
            .connect_lazy();
        let mut ingestion = Self {
            process,
            otlp: TraceServiceClient::new(otlp),
            internal_port,
            parquet_directory,
            directory,
        };
        ingestion.wait_until_listening([public_port, internal_port]);
        ingestion
    }

    /// Wait until both of the process's ports accept a connection. A panic
    /// here drops the process, which prints its log.
    fn wait_until_listening(&mut self, ports: [u16; 2]) {
        let deadline = Instant::now() + READY_TIMEOUT;
        loop {
            if let Some(status) = self.process.try_wait().unwrap() {
                panic!("ingestion stopped with {status} before it was ready");
            }
            if ports
                .iter()
                .all(|port| TcpStream::connect(("127.0.0.1", *port)).is_ok())
            {
                return;
            }
            assert!(
                Instant::now() < deadline,
                "ingestion was not ready within {READY_TIMEOUT:?}"
            );
            std::thread::sleep(Duration::from_millis(10));
        }
    }

    /// Send spans to the public OTLP endpoint with the API key, as an SDK
    /// does. Returns once ingestion has accepted them.
    pub async fn export(&self, request: ExportTraceServiceRequest) {
        let mut request = Request::new(request);
        request.set_timeout(EXPORT_TIMEOUT);
        request
            .metadata_mut()
            .insert("x-junjo-api-key", MetadataValue::from_static(API_KEY));
        self.otlp
            .clone()
            .export(request)
            .await
            .expect("ingestion accepts the export");
    }
}

impl Drop for Ingestion {
    fn drop(&mut self) {
        // Killing fails only when the process has already stopped. Waiting
        // reaps it, so its files are closed before the directory is removed.
        let _ = self.process.kill();
        let _ = self.process.wait();
        // A failed test shows what ingestion logged.
        if std::thread::panicking() {
            let path = self.directory.path().join("ingestion.log");
            match std::fs::read_to_string(&path) {
                Ok(log) => eprintln!("ingestion log:\n{log}"),
                Err(error) => eprintln!("cannot read {}: {error}", path.display()),
            }
        }
    }
}

/// Two TCP ports that are free now.
fn free_ports() -> (u16, u16) {
    let first = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let second = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    (
        first.local_addr().unwrap().port(),
        second.local_addr().unwrap().port(),
    )
}

/// The ingestion release binary, built once per test process on first use.
fn ingestion_binary() -> &'static Path {
    static BINARY: OnceLock<PathBuf> = OnceLock::new();
    BINARY.get_or_init(|| {
        // The server crate sits two directories below the Studio root.
        let ingestion = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../ingestion");
        let build = Command::new("cargo")
            .args(["build", "--release", "--locked"])
            .current_dir(&ingestion)
            // Under `cargo test`, rustup sets this to the toolchain this
            // workspace pins, and a nested cargo would use it too. Ingestion
            // is a separate deployable. Without the variable, rustup selects
            // the toolchain for ingestion's own directory, so this build and
            // every other build of ingestion share one set of artifacts
            // instead of replacing each other's.
            .env_remove("RUSTUP_TOOLCHAIN")
            .output()
            .expect("run cargo to build the ingestion service");
        assert!(
            build.status.success(),
            "building the ingestion service failed:\n{}",
            String::from_utf8_lossy(&build.stderr)
        );
        let binary = ingestion.join("target/release/ingestion");
        assert!(
            binary.is_file(),
            "the ingestion build left no binary at {}",
            binary.display()
        );
        binary
    })
}
