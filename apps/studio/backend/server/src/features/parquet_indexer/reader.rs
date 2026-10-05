//! Summarize one cold Parquet file for the metadata index.
//!
//! Only the five columns the index needs are read, in streaming batches. No
//! span payload or per-span object is retained: memory follows the batch size
//! and the file's distinct traces, not its row count.

use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::path::Path;

use datafusion::arrow::array::{Array, ArrayRef, AsArray, RecordBatch, StringArray};
use datafusion::arrow::compute::cast;
use datafusion::arrow::datatypes::{DataType, Int64Type, TimeUnit};
use datafusion::arrow::error::ArrowError;
use datafusion::parquet::arrow::ProjectionMask;
use datafusion::parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use datafusion::parquet::errors::ParquetError;

use super::classify::classify_attributes;
use crate::db::metadata::{FileSummary, ServiceSummary};

const METADATA_COLUMNS: [&str; 5] = [
    "trace_id",
    "service_name",
    "start_time",
    "end_time",
    "attributes",
];

#[derive(Debug, thiserror::Error)]
pub enum ReadError {
    #[error("{0}")]
    Io(#[from] std::io::Error),
    #[error("{0}")]
    Parquet(#[from] ParquetError),
    #[error("{0}")]
    Arrow(#[from] ArrowError),
    #[error("{0}")]
    InvalidData(String),
}

impl ReadError {
    /// A short stable name recorded with a failed file.
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Io(_) => "Io",
            Self::Parquet(_) => "Parquet",
            Self::Arrow(_) => "Arrow",
            Self::InvalidData(_) => "InvalidData",
        }
    }
}

/// Read and summarize the columns needed for cold file selection.
pub fn summarize_parquet_file(
    path: &Path,
    size_bytes: u64,
    batch_size: usize,
) -> Result<FileSummary, ReadError> {
    let file_path = path
        .to_str()
        .ok_or_else(|| ReadError::InvalidData("non-UTF-8 file path".to_string()))?
        .to_string();
    let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(path)?)?;
    let projection = ProjectionMask::columns(builder.parquet_schema(), METADATA_COLUMNS);
    let reader = builder
        .with_projection(projection)
        .with_batch_size(batch_size)
        .build()?;

    let mut row_count: i64 = 0;
    let mut trace_ids: HashSet<String> = HashSet::new();
    let mut services: HashMap<String, ServiceSummary> = HashMap::new();
    let mut llm_trace_ids: HashMap<String, HashSet<String>> = HashMap::new();
    let mut workflow_services: HashSet<String> = HashSet::new();
    let mut agent_services: HashSet<String> = HashSet::new();

    for batch in reader {
        let batch = batch?;
        let batch_trace_ids = text_column(&batch, "trace_id")?;
        let batch_services = text_column(&batch, "service_name")?;
        let batch_attributes = text_column(&batch, "attributes")?;
        let start_times = nanosecond_column(&batch, "start_time")?;
        let end_times = nanosecond_column(&batch, "end_time")?;
        let start_times = start_times.as_primitive::<Int64Type>();
        let end_times = end_times.as_primitive::<Int64Type>();

        for row in 0..batch.num_rows() {
            let trace_id = batch_trace_ids.value(row);
            let service = batch_services.value(row);
            let start_ns = start_times.value(row);
            let end_ns = end_times.value(row);

            if !trace_ids.contains(trace_id) {
                trace_ids.insert(trace_id.to_owned());
            }
            match services.get_mut(service) {
                Some(summary) => {
                    summary.span_count += 1;
                    summary.min_time_ns = summary.min_time_ns.min(start_ns);
                    summary.max_time_ns = summary.max_time_ns.max(end_ns);
                }
                None => {
                    services.insert(
                        service.to_owned(),
                        ServiceSummary {
                            span_count: 1,
                            min_time_ns: start_ns,
                            max_time_ns: end_ns,
                        },
                    );
                }
            }

            if batch_attributes.is_null(row) {
                continue;
            }
            let classification = classify_attributes(batch_attributes.value(row));
            if classification.is_llm {
                match llm_trace_ids.get_mut(service) {
                    Some(traces) => {
                        if !traces.contains(trace_id) {
                            traces.insert(trace_id.to_owned());
                        }
                    }
                    None => {
                        llm_trace_ids
                            .insert(service.to_owned(), HashSet::from([trace_id.to_owned()]));
                    }
                }
            }
            if classification.is_workflow && !workflow_services.contains(service) {
                workflow_services.insert(service.to_owned());
            }
            if classification.is_agent && !agent_services.contains(service) {
                agent_services.insert(service.to_owned());
            }
        }
        row_count += batch.num_rows() as i64;
    }

    if row_count == 0 {
        return Err(ReadError::InvalidData("empty Parquet file".to_string()));
    }
    let min_time_ns = services.values().map(|s| s.min_time_ns).min().unwrap_or(0);
    let max_time_ns = services.values().map(|s| s.max_time_ns).max().unwrap_or(0);
    Ok(FileSummary {
        file_path,
        size_bytes: size_bytes as i64,
        row_count,
        min_time_ns,
        max_time_ns,
        trace_ids,
        services,
        llm_trace_ids,
        workflow_services,
        agent_services,
    })
}

fn column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a ArrayRef, ReadError> {
    batch
        .column_by_name(name)
        .ok_or_else(|| ReadError::InvalidData(format!("missing column {name}")))
}

/// A text column as `Utf8`, whichever string encoding the file used.
fn text_column(batch: &RecordBatch, name: &str) -> Result<StringArray, ReadError> {
    let array = column(batch, name)?;
    let array = match array.data_type() {
        DataType::Utf8 => array.clone(),
        DataType::LargeUtf8 | DataType::Utf8View => cast(array, &DataType::Utf8)?,
        other => {
            return Err(ReadError::InvalidData(format!(
                "column {name} has unsupported type {other}"
            )));
        }
    };
    let strings = array.as_string::<i32>().clone();
    if name != "attributes" && strings.null_count() > 0 {
        return Err(ReadError::InvalidData(format!(
            "column {name} contains null values"
        )));
    }
    Ok(strings)
}

/// A nanosecond timestamp column as integers since the Unix epoch.
fn nanosecond_column(batch: &RecordBatch, name: &str) -> Result<ArrayRef, ReadError> {
    let array = column(batch, name)?;
    if !matches!(
        array.data_type(),
        DataType::Timestamp(TimeUnit::Nanosecond, _)
    ) {
        return Err(ReadError::InvalidData(format!(
            "column {name} has unsupported type {}",
            array.data_type()
        )));
    }
    if array.null_count() > 0 {
        return Err(ReadError::InvalidData(format!(
            "column {name} contains null values"
        )));
    }
    Ok(cast(array, &DataType::Int64)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::{TestSpan, write_span_parquet};

    fn names(values: &[&str]) -> HashSet<String> {
        values.iter().map(|value| value.to_string()).collect()
    }

    #[test]
    fn a_file_is_summarized_into_selection_metadata() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("spans.parquet");
        write_span_parquet(
            &path,
            &[
                TestSpan::new("trace-1", "span-1", "checkout")
                    .times(100, 500)
                    .attributes(r#"{"junjo.span_type":"workflow"}"#),
                TestSpan::new("trace-1", "span-2", "checkout")
                    .times(200, 900)
                    .attributes(r#"{"openinference.span.kind":"LLM"}"#),
                TestSpan::new("trace-2", "span-3", "billing")
                    .times(50, 300)
                    .attributes(r#"{"junjo.span_type":"agent","gen_ai.operation.name":"chat"}"#),
                TestSpan::new("trace-3", "span-4", "billing")
                    .times(400, 450)
                    .attributes("not json"),
            ],
        );
        let size_bytes = std::fs::metadata(&path).unwrap().len();

        // A two-row batch size exercises accumulation across batches.
        let summary = summarize_parquet_file(&path, size_bytes, 2).unwrap();

        assert_eq!(summary.file_path, path.to_str().unwrap());
        assert_eq!(summary.size_bytes, size_bytes as i64);
        assert_eq!(summary.row_count, 4);
        assert_eq!(summary.min_time_ns, 50);
        assert_eq!(summary.max_time_ns, 900);
        assert_eq!(summary.trace_ids, names(&["trace-1", "trace-2", "trace-3"]));
        assert_eq!(
            summary.services,
            HashMap::from([
                (
                    "checkout".to_string(),
                    ServiceSummary {
                        span_count: 2,
                        min_time_ns: 100,
                        max_time_ns: 900,
                    }
                ),
                (
                    "billing".to_string(),
                    ServiceSummary {
                        span_count: 2,
                        min_time_ns: 50,
                        max_time_ns: 450,
                    }
                ),
            ])
        );
        assert_eq!(
            summary.llm_trace_ids,
            HashMap::from([
                ("checkout".to_string(), names(&["trace-1"])),
                ("billing".to_string(), names(&["trace-2"])),
            ])
        );
        assert_eq!(summary.workflow_services, names(&["checkout"]));
        assert_eq!(summary.agent_services, names(&["billing"]));
    }

    #[test]
    fn an_empty_file_is_rejected() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("empty.parquet");
        write_span_parquet(&path, &[]);

        let error = summarize_parquet_file(&path, 1, 4096).unwrap_err();

        assert_eq!(error.kind(), "InvalidData");
        assert_eq!(error.to_string(), "empty Parquet file");
    }

    #[test]
    fn a_file_that_is_not_parquet_is_rejected() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("corrupt.parquet");
        std::fs::write(&path, b"this is not a parquet file").unwrap();

        let error = summarize_parquet_file(&path, 26, 4096).unwrap_err();

        assert_eq!(error.kind(), "Parquet");
    }

    #[test]
    fn a_missing_file_is_an_io_error() {
        let directory = tempfile::tempdir().unwrap();
        let error =
            summarize_parquet_file(&directory.path().join("missing.parquet"), 0, 4096).unwrap_err();
        assert_eq!(error.kind(), "Io");
    }
}
