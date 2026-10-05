//! Metadata indexer.
//!
//! A synchronous loop on its own thread. It owns the metadata index's writer
//! connection, so indexing concurrency is exactly one by construction
//! (ingestion ADR-002). Each cycle scans for cold Parquet files, summarizes
//! the ones not yet indexed, and records each in one transaction.

use std::ops::ControlFlow;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, RecvTimeoutError};
use std::thread;
use std::time::Duration;

use rusqlite::Connection;
use tokio::sync::oneshot;

use crate::db;
use crate::db::metadata;

pub mod classify;
pub mod reader;
pub mod scan;

#[derive(Debug, Clone)]
pub struct IndexerSettings {
    pub parquet_storage_path: PathBuf,
    pub poll_interval: Duration,
    /// Maximum files indexed per cycle.
    pub batch_size: usize,
    /// Rows per Parquet read batch.
    pub read_batch_rows: usize,
}

enum Command {
    /// Wake the thread so it sees the stop flag.
    Stop,
    /// Run one cycle now and report how many files it indexed.
    IndexNow(oneshot::Sender<Result<usize, String>>),
}

/// The running indexer thread.
pub struct Indexer {
    commands: mpsc::Sender<Command>,
    stop: Arc<AtomicBool>,
    /// Resolves when the thread ends. An error means it ended by panicking.
    pub finished: oneshot::Receiver<()>,
}

/// How a request asks the indexer thread for work.
#[derive(Clone)]
pub struct IndexerHandle {
    commands: mpsc::Sender<Command>,
}

impl IndexerHandle {
    /// Index new files now instead of at the next poll. Returns how many
    /// files were indexed. The work still runs on the indexer thread, so
    /// indexing concurrency stays at one.
    pub async fn index_now(&self) -> Result<usize, String> {
        let (reply, result) = oneshot::channel();
        self.commands
            .send(Command::IndexNow(reply))
            .map_err(|_| "the indexer is not running".to_string())?;
        result
            .await
            .map_err(|_| "the indexer stopped before it answered".to_string())?
    }

    /// A handle to no indexer: every request fails.
    #[cfg(test)]
    pub fn disconnected() -> Self {
        Self {
            commands: mpsc::channel().0,
        }
    }
}

impl Indexer {
    /// Start the indexer thread. It reconciles the index with the filesystem
    /// once, then polls.
    pub fn spawn(settings: IndexerSettings, writer: Connection) -> std::io::Result<Self> {
        let (commands, receiver) = mpsc::channel();
        let (finished_sender, finished) = oneshot::channel();
        let stop = Arc::new(AtomicBool::new(false));
        thread::Builder::new()
            .name("parquet-indexer".to_string())
            .spawn({
                let stop = stop.clone();
                move || {
                    run(settings, writer, receiver, &stop);
                    // Not reached on panic: the dropped sender reports the
                    // failure.
                    let _ = finished_sender.send(());
                }
            })?;
        Ok(Self {
            commands,
            stop,
            finished,
        })
    }

    pub fn handle(&self) -> IndexerHandle {
        IndexerHandle {
            commands: self.commands.clone(),
        }
    }

    /// Ask the thread to stop. It stops between files.
    pub fn shutdown_sender(&self) -> impl Fn() + Send + 'static {
        let commands = self.commands.clone();
        let stop = self.stop.clone();
        move || {
            stop.store(true, Ordering::Relaxed);
            let _ = commands.send(Command::Stop);
        }
    }
}

fn run(
    settings: IndexerSettings,
    mut writer: Connection,
    commands: mpsc::Receiver<Command>,
    stop: &AtomicBool,
) {
    tracing::info!(
        parquet_storage_path = %settings.parquet_storage_path.display(),
        poll_interval_seconds = settings.poll_interval.as_secs(),
        batch_size = settings.batch_size,
        "starting parquet indexer"
    );
    match sync_with_filesystem(&mut writer, &settings.parquet_storage_path) {
        Ok(removed) if removed > 0 => {
            tracing::info!(removed, "removed orphaned entries from metadata index");
        }
        Ok(_) => {}
        Err(error) => tracing::error!(%error, "metadata index reconciliation failed"),
    }

    loop {
        // Wait one poll interval, or act on a request before it elapses.
        let requested = match commands.recv_timeout(settings.poll_interval) {
            Ok(Command::Stop) | Err(RecvTimeoutError::Disconnected) => break,
            Ok(Command::IndexNow(reply)) => Some(reply),
            Err(RecvTimeoutError::Timeout) => None,
        };
        let cycle = index_new_files(&mut writer, &settings, || stop.load(Ordering::Relaxed));
        let (answer, stopping) = match cycle {
            Ok(ControlFlow::Continue(indexed)) => (Ok(indexed), false),
            Ok(ControlFlow::Break(())) => (Err("the indexer is stopping".to_string()), true),
            // Keep polling: the next cycle retries.
            Err(error) => {
                tracing::error!(%error, "error in indexer cycle");
                (Err(error.to_string()), false)
            }
        };
        if let Some(reply) = requested {
            // The requester may have gone away; the cycle still ran.
            let _ = reply.send(answer);
        }
        if stopping {
            break;
        }
    }

    if let Err(error) = db::checkpoint(&writer) {
        tracing::warn!(%error, "metadata WAL checkpoint failed");
    }
    tracing::info!("parquet indexer stopped");
}

/// Remove index entries whose files no longer exist. Returns how many were
/// removed. A missing storage directory leaves the index untouched.
pub fn sync_with_filesystem(
    writer: &mut Connection,
    parquet_storage_path: &Path,
) -> rusqlite::Result<usize> {
    if !parquet_storage_path.is_dir() {
        tracing::warn!(
            path = %parquet_storage_path.display(),
            "Parquet storage path is not a directory; skipping metadata filesystem sync"
        );
        return Ok(0);
    }
    let on_disk: std::collections::HashSet<String> = scan::scan_parquet_files(parquet_storage_path)
        .into_iter()
        .map(|file| file.path)
        .collect();
    let orphaned: Vec<String> = metadata::indexed_file_paths(writer)?
        .into_iter()
        .filter(|path| !on_disk.contains(path))
        .collect();
    if orphaned.is_empty() {
        return Ok(0);
    }
    metadata::remove_files(writer, &orphaned)
}

/// Index up to one batch of new files. `stop_requested` is checked between
/// files. Returns how many files were indexed, or `Break` when asked to stop.
pub fn index_new_files(
    writer: &mut Connection,
    settings: &IndexerSettings,
    stop_requested: impl Fn() -> bool,
) -> rusqlite::Result<ControlFlow<(), usize>> {
    let all_files = scan::scan_parquet_files(&settings.parquet_storage_path);
    if all_files.is_empty() {
        return Ok(ControlFlow::Continue(0));
    }
    let indexed = metadata::indexed_file_paths(writer)?;
    // Known bad files are not retried.
    let failed = metadata::failed_file_paths(writer)?;
    let total_files = all_files.len();
    let new_files: Vec<scan::ParquetFile> = all_files
        .into_iter()
        .filter(|file| !indexed.contains(&file.path) && !failed.contains(&file.path))
        .collect();
    if new_files.is_empty() {
        return Ok(ControlFlow::Continue(0));
    }
    tracing::info!(
        total_files,
        already_indexed = indexed.len(),
        new_files = new_files.len(),
        "found new parquet files to index"
    );

    let mut indexed_count = 0;
    for file in new_files.iter().take(settings.batch_size) {
        if stop_requested() {
            return Ok(ControlFlow::Break(()));
        }
        let summary = match reader::summarize_parquet_file(
            Path::new(&file.path),
            file.size_bytes,
            settings.read_batch_rows,
        ) {
            Ok(summary) => summary,
            Err(error) => {
                record_failure(writer, file, error.kind(), &error.to_string());
                continue;
            }
        };
        match metadata::index_file(writer, &summary) {
            Ok(file_id) => {
                indexed_count += 1;
                tracing::info!(
                    file_path = %file.path,
                    file_id,
                    spans = summary.row_count,
                    traces = summary.trace_ids.len(),
                    services = summary.services.len(),
                    "indexed parquet file"
                );
            }
            Err(error) => record_failure(writer, file, "Sqlite", &error.to_string()),
        }
    }
    Ok(ControlFlow::Continue(indexed_count))
}

fn record_failure(writer: &Connection, file: &scan::ParquetFile, kind: &str, message: &str) {
    tracing::error!(
        file_path = %file.path,
        file_size = file.size_bytes,
        error_type = kind,
        error = message,
        "failed to index parquet file"
    );
    if let Err(error) =
        metadata::record_failed_file(writer, &file.path, kind, message, file.size_bytes as i64)
    {
        tracing::warn!(file_path = %file.path, %error, "failed to record failed file");
    }
}

#[cfg(test)]
mod tests {
    use std::time::Instant;

    use super::*;
    use crate::test_support::{TestSpan, write_span_parquet};

    struct Fixture {
        directory: tempfile::TempDir,
        writer: Connection,
        settings: IndexerSettings,
    }

    fn fixture(batch_size: usize) -> Fixture {
        let directory = tempfile::tempdir().unwrap();
        let metadata = db::open_metadata_db(&directory.path().join("metadata.db")).unwrap();
        let settings = IndexerSettings {
            parquet_storage_path: directory.path().join("parquet"),
            poll_interval: Duration::from_millis(20),
            batch_size,
            read_batch_rows: 4096,
        };
        std::fs::create_dir_all(&settings.parquet_storage_path).unwrap();
        Fixture {
            directory,
            writer: metadata.writer,
            settings,
        }
    }

    fn write_file(fixture: &Fixture, name: &str) -> PathBuf {
        let path = fixture
            .settings
            .parquet_storage_path
            .join("year=2026/month=10/day=03")
            .join(name);
        write_span_parquet(&path, &[TestSpan::new(name, "span-1", "checkout")]);
        path
    }

    fn count(connection: &Connection, table: &str) -> i64 {
        connection
            .query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |row| {
                row.get(0)
            })
            .unwrap()
    }

    fn cycle(fixture: &mut Fixture) -> ControlFlow<(), usize> {
        index_new_files(&mut fixture.writer, &fixture.settings, || false).unwrap()
    }

    #[test]
    fn new_files_are_indexed_up_to_the_batch_size_per_cycle() {
        let mut fixture = fixture(2);
        write_file(&fixture, "a.parquet");
        write_file(&fixture, "b.parquet");
        write_file(&fixture, "c.parquet");

        assert_eq!(cycle(&mut fixture), ControlFlow::Continue(2));
        assert_eq!(cycle(&mut fixture), ControlFlow::Continue(1));
        assert_eq!(cycle(&mut fixture), ControlFlow::Continue(0));
        assert_eq!(count(&fixture.writer, "parquet_files"), 3);
    }

    #[test]
    fn a_corrupt_file_is_recorded_as_failed_and_not_retried() {
        let mut fixture = fixture(10);
        write_file(&fixture, "good.parquet");
        let corrupt = fixture
            .settings
            .parquet_storage_path
            .join("corrupt.parquet");
        std::fs::write(&corrupt, b"not parquet").unwrap();

        assert_eq!(cycle(&mut fixture), ControlFlow::Continue(1));
        assert_eq!(cycle(&mut fixture), ControlFlow::Continue(0));

        let (path, kind, retries): (String, String, i64) = fixture
            .writer
            .query_row(
                "SELECT file_path, error_type, retry_count FROM failed_parquet_files",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(path, corrupt.to_str().unwrap());
        assert_eq!(kind, "Parquet");
        assert_eq!(retries, 1);
    }

    #[test]
    fn a_stop_request_ends_the_cycle_before_the_next_file() {
        let mut fixture = fixture(10);
        write_file(&fixture, "a.parquet");

        let outcome = index_new_files(&mut fixture.writer, &fixture.settings, || true).unwrap();

        assert_eq!(outcome, ControlFlow::Break(()));
        assert_eq!(count(&fixture.writer, "parquet_files"), 0);
    }

    #[test]
    fn a_missing_storage_directory_is_an_empty_cycle() {
        let mut fixture = fixture(10);
        fixture.settings.parquet_storage_path = fixture.directory.path().join("not-created-yet");
        assert_eq!(cycle(&mut fixture), ControlFlow::Continue(0));
    }

    #[test]
    fn reconciliation_removes_entries_for_deleted_files() {
        let mut fixture = fixture(10);
        let kept = write_file(&fixture, "kept.parquet");
        let deleted = write_file(&fixture, "deleted.parquet");
        assert_eq!(cycle(&mut fixture), ControlFlow::Continue(2));
        std::fs::remove_file(&deleted).unwrap();

        let removed =
            sync_with_filesystem(&mut fixture.writer, &fixture.settings.parquet_storage_path)
                .unwrap();

        assert_eq!(removed, 1);
        assert_eq!(
            metadata::indexed_file_paths(&fixture.writer).unwrap(),
            std::collections::HashSet::from([kept.to_str().unwrap().to_string()])
        );
        assert_eq!(count(&fixture.writer, "trace_files"), 1);
    }

    #[tokio::test]
    async fn the_thread_indexes_new_files_and_stops_when_asked() {
        let fixture = fixture(10);
        write_file(&fixture, "a.parquet");
        let observer = Connection::open(fixture.directory.path().join("metadata.db")).unwrap();

        let indexer = Indexer::spawn(fixture.settings.clone(), fixture.writer).unwrap();
        let deadline = Instant::now() + Duration::from_secs(10);
        while count(&observer, "parquet_files") == 0 {
            assert!(Instant::now() < deadline, "file was not indexed in time");
            tokio::time::sleep(Duration::from_millis(10)).await;
        }

        (indexer.shutdown_sender())();
        indexer
            .finished
            .await
            .expect("indexer thread stopped cleanly");
        assert_eq!(count(&observer, "parquet_files"), 1);
    }

    #[tokio::test]
    async fn a_request_indexes_at_once_and_reports_the_count() {
        let mut fixture = fixture(10);
        // Far longer than the test: only a request can start a cycle.
        fixture.settings.poll_interval = Duration::from_secs(3600);
        write_file(&fixture, "a.parquet");
        write_file(&fixture, "b.parquet");

        let indexer = Indexer::spawn(fixture.settings.clone(), fixture.writer).unwrap();
        let handle = indexer.handle();
        assert_eq!(handle.index_now().await, Ok(2));
        assert_eq!(handle.index_now().await, Ok(0));

        (indexer.shutdown_sender())();
        indexer
            .finished
            .await
            .expect("indexer thread stopped cleanly");
        assert!(handle.index_now().await.is_err());
        assert!(IndexerHandle::disconnected().index_now().await.is_err());
    }
}
