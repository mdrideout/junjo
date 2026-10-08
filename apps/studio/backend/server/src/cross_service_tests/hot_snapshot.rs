//! The hot snapshot: the Parquet file of unflushed spans that ingestion
//! prepares for a query, as the backend's ingestion client reports it.

use std::fs::File;

use datafusion::parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;

use super::{harness, otlp};
use crate::features::span_ingestion::IngestionQueryContext;
use crate::test_support::{span_schema, test_app};

const SERVICE: &str = "svc-hot-snapshot";
const TRACE_ID: &str = "5b8aa5a2d2c872e8321cf37308d69df2";
const SPAN_IDS: [&str; 3] = ["051581bf3cb55c11", "051581bf3cb55c12", "051581bf3cb55c13"];

#[tokio::test]
async fn unflushed_spans_are_reported_as_one_parquet_snapshot_at_a_fixed_path() {
    let (app, ingestion) = harness::start().await;
    let client = &app.state.ingestion;

    // An empty write-ahead log has nothing to snapshot.
    assert_eq!(
        client.query_context().await,
        IngestionQueryContext::default()
    );

    let spans = SPAN_IDS
        .iter()
        .map(|span_id| otlp::span(TRACE_ID, span_id, "span"))
        .collect();
    ingestion.export(otlp::export_request(SERVICE, spans)).await;

    let context = client.query_context().await;
    assert_eq!(context.recent_cold_paths, Vec::<String>::new());
    let snapshot = context.hot_snapshot_path.expect("a hot snapshot");
    assert!(snapshot.ends_with(".parquet"), "{snapshot}");

    // The file is Parquet with every stored span column, and one row for
    // each unflushed span.
    let reader = ParquetRecordBatchReaderBuilder::try_new(File::open(&snapshot).unwrap()).unwrap();
    for column in span_schema().fields() {
        assert_eq!(
            reader.schema().field_with_name(column.name()).unwrap(),
            column.as_ref()
        );
    }
    assert_eq!(reader.metadata().file_metadata().num_rows(), 3);

    // Every request reports the same path.
    assert_eq!(
        client.query_context().await.hot_snapshot_path,
        Some(snapshot)
    );
}

#[tokio::test]
async fn a_snapshot_request_that_cannot_reach_ingestion_reports_no_hot_tier() {
    // A test application's ingestion client points at a port nothing listens
    // on.
    let app = test_app();

    let context = app.state.ingestion.query_context().await;

    assert_eq!(context, IngestionQueryContext::default());
}
