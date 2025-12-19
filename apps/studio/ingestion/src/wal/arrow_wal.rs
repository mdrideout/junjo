use std::fs::File;
use std::io::BufReader;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use arrow::array::{
    ArrayRef, Int64Array, Int8Array, RecordBatch, StringArray,
    TimestampNanosecondArray,
};
use arrow::ipc::reader::StreamReader;
use arrow::ipc::writer::StreamWriter;
use parquet::arrow::ArrowWriter;
use parquet::basic::Compression;
use parquet::file::properties::WriterProperties;
use thiserror::Error;
use tracing::{debug, info, warn};

use super::schema::SPAN_SCHEMA;
use super::span_record::SpanRecord;

#[derive(Error, Debug)]
pub enum WalError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("Arrow error: {0}")]
    Arrow(#[from] arrow::error::ArrowError),
    #[error("Parquet error: {0}")]
    Parquet(#[from] parquet::errors::ParquetError),
}

/// How often to flush pending spans to IPC even if batch isn't full (for durability).
const FLUSH_INTERVAL: Duration = Duration::from_secs(3);

/// Arrow IPC Segmented Write-Ahead Log for span data.
///
/// Uses a segmented log pattern where each batch is written to a separate IPC file.
/// This provides constant memory usage during reads - only one segment is loaded at a time.
///
/// Directory structure:
///   wal/
///     batch_1734482100000000001.ipc  (~1-2MB)
///     batch_1734482103000000002.ipc  (~1-2MB)
///     ...
///
/// Write triggers (any of):
/// - Span count reached (BATCH_SIZE, default 1000)
/// - Timer expired (3 seconds) with pending spans
///
/// Atomic safety:
/// - Segments are written to .ipc.tmp first, then atomically renamed to .ipc
/// - list_segments() only returns .ipc files (ignores .tmp)
/// - Flusher never sees incomplete segments
pub struct ArrowWal {
    /// Directory containing IPC segment files
    wal_dir: PathBuf,
    /// In-memory buffer of pending spans (not yet written to IPC)
    pending: Vec<SpanRecord>,
    /// Max spans per segment
    batch_size: usize,
    /// Cached total size of all segment files
    total_size: u64,
    /// Last time we flushed pending spans to IPC
    last_flush: Instant,
    /// Counter for unique file names (combined with timestamp)
    sequence: u64,
}

impl ArrowWal {
    /// Create a new ArrowWal using the given directory for segment files.
    pub fn new(wal_dir: &Path, batch_size: usize) -> Result<Self, WalError> {
        // Ensure WAL directory exists
        std::fs::create_dir_all(wal_dir)?;

        // Calculate total size of existing segment files
        let total_size = Self::calculate_total_size(wal_dir)?;
        let segment_count = Self::count_segments(wal_dir)?;

        info!(
            wal_dir = %wal_dir.display(),
            batch_size = batch_size,
            existing_segments = segment_count,
            existing_size_mb = total_size / 1024 / 1024,
            flush_interval_secs = FLUSH_INTERVAL.as_secs(),
            "Initialized Arrow WAL (Segmented Log mode)"
        );

        Ok(Self {
            wal_dir: wal_dir.to_path_buf(),
            pending: Vec::with_capacity(batch_size.min(10000)), // Cap initial capacity
            batch_size,
            total_size,
            last_flush: Instant::now(),
            sequence: 0,
        })
    }

    /// Add a span to the WAL. Returns true if a batch was flushed to IPC.
    pub fn write_span(&mut self, record: SpanRecord) -> Result<bool, WalError> {
        self.pending.push(record);

        // Flush only when batch is full
        // Timer-based flush is handled externally by the flusher checking needs_timer_flush()
        if self.pending.len() >= self.batch_size {
            self.flush_pending()?;
            return Ok(true);
        }

        Ok(false)
    }

    /// Add multiple spans to the WAL. Returns true if any segment was written.
    pub fn write_spans(&mut self, records: Vec<SpanRecord>) -> Result<bool, WalError> {
        let mut segment_written = false;
        for record in records {
            if self.write_span(record)? {
                segment_written = true;
            }
        }
        Ok(segment_written)
    }

    /// Flush pending spans to a new IPC segment file.
    /// Uses atomic rename: writes to .ipc.tmp, then renames to .ipc when complete.
    pub fn flush_pending(&mut self) -> Result<(), WalError> {
        if self.pending.is_empty() {
            return Ok(());
        }

        let batch = self.build_record_batch(&self.pending)?;
        let batch_rows = batch.num_rows();

        // Generate unique segment filename (final path)
        let segment_path = self.generate_segment_path();

        // Write batch to new segment file (uses atomic rename internally)
        self.write_segment(&segment_path, &batch)?;

        // Update state
        let segment_size = std::fs::metadata(&segment_path)?.len();
        self.total_size += segment_size;
        self.pending.clear();
        self.last_flush = Instant::now();

        debug!(
            segment = %segment_path.display(),
            rows = batch_rows,
            segment_size_kb = segment_size / 1024,
            total_size_mb = self.total_size / 1024 / 1024,
            "Written new WAL segment"
        );

        Ok(())
    }

    /// Get the total size of all segment files in bytes.
    pub fn file_size(&self) -> u64 {
        self.total_size
    }

    /// Check if timer-based flush is needed (called externally).
    pub fn needs_timer_flush(&self) -> bool {
        !self.pending.is_empty() && self.last_flush.elapsed() >= FLUSH_INTERVAL
    }

    /// Read all record batches from all segment files.
    /// Memory efficient: processes one segment at a time.
    /// Note: Used only in tests; production uses streaming flush.
    #[allow(dead_code)]
    pub fn read_batches(&mut self) -> Result<Vec<RecordBatch>, WalError> {
        // First flush any pending data
        self.flush_pending()?;

        let segments = self.list_segments()?;
        if segments.is_empty() {
            return Ok(Vec::new());
        }

        let mut batches = Vec::new();
        for segment_path in &segments {
            let segment_batches = self.read_segment(segment_path)?;
            batches.extend(segment_batches);
        }

        debug!(
            segments = segments.len(),
            total_rows = batches.iter().map(|b| b.num_rows()).sum::<usize>(),
            "Read all batches from WAL segments"
        );

        Ok(batches)
    }

    /// Flush WAL segments to a Parquet file with streaming (constant memory).
    /// Reads one segment at a time, writes to parquet, drops memory before next segment.
    /// Deletes only the segments that were flushed (new segments created during flush are preserved).
    /// Returns row_count, or 0 if WAL is empty.
    pub fn flush_to_parquet(&mut self, output_path: &Path) -> Result<i64, WalError> {
        self.flush_pending()?;

        // SNAPSHOT: capture segments to flush (new segments created during flush won't be included)
        let segments_to_flush = self.list_segments()?;
        if segments_to_flush.is_empty() {
            return Ok(0);
        }

        // Ensure parent directory exists
        if let Some(parent) = output_path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        // Write to temp file first, then atomic rename
        let temp_path = output_path.with_extension("parquet.tmp");

        let props = WriterProperties::builder()
            .set_compression(Compression::LZ4_RAW)
            .set_max_row_group_size(122880)
            .build();

        let file = File::create(&temp_path)?;
        let mut writer = ArrowWriter::try_new(file, SPAN_SCHEMA.clone(), Some(props))?;

        let mut row_count: i64 = 0;

        // Stream one segment at a time (constant memory)
        for segment_path in &segments_to_flush {
            let batches = self.read_segment(segment_path)?;
            for batch in batches {
                row_count += batch.num_rows() as i64;
                writer.write(&batch)?;
            }
            // batch and segment data dropped before next iteration
        }

        writer.close()?;
        std::fs::rename(&temp_path, output_path)?;

        // Delete ONLY the segments we just flushed (preserves any new segments created during flush)
        for segment_path in &segments_to_flush {
            if let Err(e) = std::fs::remove_file(segment_path) {
                warn!(segment = %segment_path.display(), error = %e, "Failed to delete flushed segment");
            }
        }

        // Recalculate total_size (new segments may have been created during flush)
        self.total_size = Self::calculate_total_size(&self.wal_dir)?;

        debug!(
            output_path = %output_path.display(),
            segments_flushed = segments_to_flush.len(),
            row_count = row_count,
            remaining_size_mb = self.total_size / 1024 / 1024,
            "Flushed WAL to Parquet (streaming)"
        );

        Ok(row_count)
    }

    /// Create a stable Parquet snapshot of the current WAL for backend to read directly.
    /// Memory efficient: streams one segment at a time to parquet.
    /// Returns (row_count, file_size_bytes).
    pub fn create_snapshot(&mut self, snapshot_path: &Path) -> Result<(i64, u64), WalError> {
        // First flush any pending data to a segment
        self.flush_pending()?;

        let segments = self.list_segments()?;

        // If WAL is empty, remove old snapshot if exists
        if segments.is_empty() {
            if snapshot_path.exists() {
                std::fs::remove_file(snapshot_path)?;
            }
            return Ok((0, 0));
        }

        // Ensure parent directory exists
        if let Some(parent) = snapshot_path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        // Write to temp file first, then atomic rename
        let temp_path = snapshot_path.with_extension("parquet.tmp");

        // Configure parquet writer - optimized for DataFusion queries
        let props = WriterProperties::builder()
            .set_compression(Compression::LZ4_RAW)
            .set_max_row_group_size(122880)
            .build();

        let output_file = File::create(&temp_path)?;
        let mut writer = ArrowWriter::try_new(output_file, SPAN_SCHEMA.clone(), Some(props))?;

        let mut row_count: i64 = 0;

        // Stream each segment to parquet (constant memory)
        for segment_path in &segments {
            let batches = self.read_segment(segment_path)?;
            for batch in batches {
                row_count += batch.num_rows() as i64;
                writer.write(&batch)?;
                // batch is dropped here, freeing memory before next iteration
            }
            // segment data freed before reading next segment
        }

        writer.close()?;

        // Atomic rename - prevents backend from seeing partial file
        std::fs::rename(&temp_path, snapshot_path)?;

        let file_size = std::fs::metadata(snapshot_path)?.len();

        info!(
            snapshot_path = %snapshot_path.display(),
            segments = segments.len(),
            row_count = row_count,
            file_size_bytes = file_size,
            "Created hot Parquet snapshot (streaming)"
        );

        Ok((row_count, file_size))
    }

    /// Truncate the WAL by deleting all segment files.
    /// Note: Used only in tests; production uses streaming flush with selective deletion.
    #[allow(dead_code)]
    pub fn truncate(&mut self) -> Result<(), WalError> {
        let segments = self.list_segments()?;
        let count = segments.len();

        for segment_path in segments {
            std::fs::remove_file(segment_path)?;
        }

        self.total_size = 0;
        self.pending.clear();
        self.last_flush = Instant::now();

        info!(
            wal_dir = %self.wal_dir.display(),
            segments_deleted = count,
            "Truncated WAL (deleted all segments)"
        );

        Ok(())
    }

    /// Generate a unique segment file path.
    fn generate_segment_path(&mut self) -> PathBuf {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        self.sequence += 1;

        self.wal_dir.join(format!("batch_{}_{:04}.ipc", timestamp, self.sequence))
    }

    /// Write a single batch to a new segment file.
    /// Uses atomic rename: writes to .ipc.tmp, then renames to .ipc when complete.
    /// This ensures list_segments() never sees incomplete segments.
    fn write_segment(&self, final_path: &Path, batch: &RecordBatch) -> Result<(), WalError> {
        // Write to temp file first
        let tmp_path = final_path.with_extension("ipc.tmp");
        let file = File::create(&tmp_path)?;
        let mut writer = StreamWriter::try_new(file, &SPAN_SCHEMA)?;
        writer.write(batch)?;
        writer.finish()?;

        // Atomic rename - segment is now visible to flusher/readers
        std::fs::rename(&tmp_path, final_path)?;
        Ok(())
    }

    /// Read all batches from a single segment file.
    fn read_segment(&self, path: &Path) -> Result<Vec<RecordBatch>, WalError> {
        let file = File::open(path)?;
        let reader = StreamReader::try_new(BufReader::new(file), None)?;

        let mut batches = Vec::new();
        for batch_result in reader {
            batches.push(batch_result?);
        }
        Ok(batches)
    }

    /// List all segment files sorted by name (timestamp order).
    fn list_segments(&self) -> Result<Vec<PathBuf>, WalError> {
        let mut segments: Vec<PathBuf> = std::fs::read_dir(&self.wal_dir)?
            .filter_map(|entry| entry.ok())
            .map(|entry| entry.path())
            .filter(|path| {
                path.extension()
                    .map(|ext| ext == "ipc")
                    .unwrap_or(false)
            })
            .collect();

        // Sort by filename (timestamp-based names sort correctly)
        segments.sort();
        Ok(segments)
    }

    /// Calculate total size of all segment files.
    fn calculate_total_size(wal_dir: &Path) -> Result<u64, WalError> {
        let mut total = 0u64;
        for entry in std::fs::read_dir(wal_dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.extension().map(|ext| ext == "ipc").unwrap_or(false) {
                total += std::fs::metadata(&path)?.len();
            }
        }
        Ok(total)
    }

    /// Count existing segment files.
    fn count_segments(wal_dir: &Path) -> Result<usize, WalError> {
        let count = std::fs::read_dir(wal_dir)?
            .filter_map(|entry| entry.ok())
            .filter(|entry| {
                entry.path()
                    .extension()
                    .map(|ext| ext == "ipc")
                    .unwrap_or(false)
            })
            .count();
        Ok(count)
    }

    /// Build an Arrow RecordBatch from SpanRecords.
    fn build_record_batch(&self, records: &[SpanRecord]) -> Result<RecordBatch, WalError> {
        // Build arrays for each column
        let span_ids: StringArray = records.iter().map(|r| Some(r.span_id.as_str())).collect();
        let trace_ids: StringArray = records.iter().map(|r| Some(r.trace_id.as_str())).collect();
        let parent_span_ids: StringArray = records
            .iter()
            .map(|r| r.parent_span_id.as_deref())
            .collect();
        let service_names: StringArray = records
            .iter()
            .map(|r| Some(r.service_name.as_str()))
            .collect();
        let names: StringArray = records.iter().map(|r| Some(r.name.as_str())).collect();
        let span_kinds: Int8Array = records.iter().map(|r| Some(r.span_kind)).collect();
        let start_times: TimestampNanosecondArray = records
            .iter()
            .map(|r| Some(r.start_time_ns))
            .collect::<TimestampNanosecondArray>()
            .with_timezone("UTC");
        let end_times: TimestampNanosecondArray = records
            .iter()
            .map(|r| Some(r.end_time_ns))
            .collect::<TimestampNanosecondArray>()
            .with_timezone("UTC");
        let durations: Int64Array = records.iter().map(|r| Some(r.duration_ns)).collect();
        let status_codes: Int8Array = records.iter().map(|r| Some(r.status_code)).collect();
        let status_messages: StringArray = records
            .iter()
            .map(|r| r.status_message.as_deref())
            .collect();
        let attributes: StringArray = records
            .iter()
            .map(|r| Some(r.attributes.as_str()))
            .collect();
        let events: StringArray = records.iter().map(|r| Some(r.events.as_str())).collect();
        let resource_attrs: StringArray = records
            .iter()
            .map(|r| Some(r.resource_attributes.as_str()))
            .collect();

        let columns: Vec<ArrayRef> = vec![
            Arc::new(span_ids),
            Arc::new(trace_ids),
            Arc::new(parent_span_ids),
            Arc::new(service_names),
            Arc::new(names),
            Arc::new(span_kinds),
            Arc::new(start_times),
            Arc::new(end_times),
            Arc::new(durations),
            Arc::new(status_codes),
            Arc::new(status_messages),
            Arc::new(attributes),
            Arc::new(events),
            Arc::new(resource_attrs),
        ];

        let batch = RecordBatch::try_new(SPAN_SCHEMA.clone(), columns)?;
        Ok(batch)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn test_record() -> SpanRecord {
        SpanRecord {
            span_id: "abc123".to_string(),
            trace_id: "trace456".to_string(),
            parent_span_id: None,
            service_name: "test-service".to_string(),
            name: "test-span".to_string(),
            span_kind: 1,
            start_time_ns: 1000000000,
            end_time_ns: 2000000000,
            duration_ns: 1000000000,
            status_code: 0,
            status_message: None,
            attributes: "{}".to_string(),
            events: "[]".to_string(),
            resource_attributes: "{}".to_string(),
        }
    }

    #[test]
    fn test_write_and_read() {
        let dir = tempdir().unwrap();
        let wal_dir = dir.path().join("wal");

        let mut wal = ArrowWal::new(&wal_dir, 10).unwrap();

        // Write some records
        for _ in 0..5 {
            wal.write_span(test_record()).unwrap();
        }

        // Flush and read
        wal.flush_pending().unwrap();
        let batches = wal.read_batches().unwrap();

        assert_eq!(batches.len(), 1);
        assert_eq!(batches[0].num_rows(), 5);
    }

    #[test]
    fn test_multiple_segments() {
        let dir = tempdir().unwrap();
        let wal_dir = dir.path().join("wal");

        // batch_size=3 means segments flush every 3 spans
        let mut wal = ArrowWal::new(&wal_dir, 3).unwrap();

        // Write 10 records with batch_size=3, should create multiple segments
        for _ in 0..10 {
            wal.write_span(test_record()).unwrap();
        }
        wal.flush_pending().unwrap();

        // Should have 4 segments (3+3+3+1)
        let segments = wal.list_segments().unwrap();
        assert_eq!(segments.len(), 4);

        // Should read all 10 records
        let batches = wal.read_batches().unwrap();
        let total_rows: usize = batches.iter().map(|b| b.num_rows()).sum();
        assert_eq!(total_rows, 10);
    }

    #[test]
    fn test_truncate() {
        let dir = tempdir().unwrap();
        let wal_dir = dir.path().join("wal");

        let mut wal = ArrowWal::new(&wal_dir, 10).unwrap();

        wal.write_span(test_record()).unwrap();
        wal.flush_pending().unwrap();

        assert!(wal.file_size() > 0);

        wal.truncate().unwrap();

        assert_eq!(wal.file_size(), 0);
        assert_eq!(wal.list_segments().unwrap().len(), 0);
    }
}
