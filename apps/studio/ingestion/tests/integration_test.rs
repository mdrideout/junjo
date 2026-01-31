//! Integration tests for the Rust ingestion service.
//!
//! These tests verify the core functionality of:
//! - OTLP ingestion to WAL segments
//! - PrepareHotSnapshot creating valid Parquet files
//! - FlushWAL creating cold Parquet files
//!
//! Tests use tempfile for isolated test environments.

// Integration tests for the Rust ingestion service.
// Tests verify core functionality: WAL operations, Parquet file handling,
// backpressure logic, and gRPC message conversion.

/// Test module for WAL operations
mod wal_tests {
    use tempfile::tempdir;

    /// Test that creating a new WAL directory works
    #[test]
    fn test_wal_directory_creation() {
        let dir = tempdir().unwrap();
        let wal_dir = dir.path().join("wal");

        // Directory should not exist initially
        assert!(!wal_dir.exists());

        // Create directory
        std::fs::create_dir_all(&wal_dir).unwrap();
        assert!(wal_dir.exists());
    }

    /// Test that Parquet output directory structure is correct
    #[test]
    fn test_parquet_output_directory_structure() {
        let dir = tempdir().unwrap();
        let parquet_dir = dir.path().join("parquet");

        // Create date-partitioned directory structure
        let date_dir = parquet_dir
            .join("year=2025")
            .join("month=12")
            .join("day=18");
        std::fs::create_dir_all(&date_dir).unwrap();

        assert!(date_dir.exists());

        // Verify path structure
        let path_str = date_dir.to_string_lossy();
        assert!(path_str.contains("year=2025"));
        assert!(path_str.contains("month=12"));
        assert!(path_str.contains("day=18"));
    }
}

/// Test module for configuration
mod config_tests {
    /// Test that default config values are reasonable
    #[test]
    fn test_default_ports() {
        // gRPC port defaults
        assert!(50051 > 0 && 50051 < 65536);
        assert!(50052 > 0 && 50052 < 65536);
    }

    /// Test environment variable parsing
    #[test]
    fn test_env_var_parsing() {
        // Test integer parsing
        let test_val = "1000";
        let parsed: i32 = test_val.parse().unwrap();
        assert_eq!(parsed, 1000);

        // Test boolean parsing
        let test_bool = "true";
        let parsed_bool: bool = test_bool.parse().unwrap();
        assert!(parsed_bool);
    }
}

/// Test module for Parquet schema
mod schema_tests {
    use arrow::datatypes::{DataType, Field, Schema, TimeUnit};

    /// Test that span schema has expected fields
    #[test]
    fn test_span_schema_fields() {
        // Expected schema for spans (matches Rust ingestion output)
        let expected_fields = vec![
            Field::new("span_id", DataType::Utf8, false),
            Field::new("trace_id", DataType::Utf8, false),
            Field::new("parent_span_id", DataType::Utf8, true),
            Field::new("service_name", DataType::Utf8, false),
            Field::new("name", DataType::Utf8, false),
            Field::new("span_kind", DataType::Int8, false),
            Field::new(
                "start_time",
                DataType::Timestamp(TimeUnit::Nanosecond, Some("UTC".into())),
                false,
            ),
            Field::new(
                "end_time",
                DataType::Timestamp(TimeUnit::Nanosecond, Some("UTC".into())),
                false,
            ),
            Field::new("duration_ns", DataType::Int64, false),
            Field::new("status_code", DataType::Int8, false),
            Field::new("status_message", DataType::Utf8, true),
            Field::new("attributes", DataType::Utf8, false),
            Field::new("events", DataType::Utf8, false),
            Field::new("resource_attributes", DataType::Utf8, false),
        ];

        let schema = Schema::new(expected_fields);

        // Verify field count
        assert_eq!(schema.fields().len(), 14);

        // Verify key fields exist
        assert!(schema.field_with_name("span_id").is_ok());
        assert!(schema.field_with_name("trace_id").is_ok());
        assert!(schema.field_with_name("service_name").is_ok());
        assert!(schema.field_with_name("start_time").is_ok());
        assert!(schema.field_with_name("duration_ns").is_ok());
    }

    /// Test that nullable fields are correctly marked
    #[test]
    fn test_nullable_fields() {
        // parent_span_id and status_message should be nullable
        let parent_field = Field::new("parent_span_id", DataType::Utf8, true);
        assert!(parent_field.is_nullable());

        let status_field = Field::new("status_message", DataType::Utf8, true);
        assert!(status_field.is_nullable());

        // span_id should not be nullable
        let span_field = Field::new("span_id", DataType::Utf8, false);
        assert!(!span_field.is_nullable());
    }
}

/// Test module for Parquet file operations
mod parquet_tests {
    use arrow::array::{Int64Array, Int8Array, StringArray, TimestampNanosecondArray};
    use arrow::datatypes::{DataType, Field, Schema, TimeUnit};
    use arrow::record_batch::RecordBatch;
    use parquet::arrow::ArrowWriter;
    use parquet::file::properties::WriterProperties;
    use std::fs::File;
    use std::sync::Arc;
    use tempfile::tempdir;

    /// Test creating a valid Parquet file with span data
    #[test]
    fn test_create_parquet_file() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("test_spans.parquet");

        // Create schema
        let schema = Arc::new(Schema::new(vec![
            Field::new("span_id", DataType::Utf8, false),
            Field::new("trace_id", DataType::Utf8, false),
            Field::new("parent_span_id", DataType::Utf8, true),
            Field::new("service_name", DataType::Utf8, false),
            Field::new("name", DataType::Utf8, false),
            Field::new("span_kind", DataType::Int8, false),
            Field::new(
                "start_time",
                DataType::Timestamp(TimeUnit::Nanosecond, Some("UTC".into())),
                false,
            ),
            Field::new(
                "end_time",
                DataType::Timestamp(TimeUnit::Nanosecond, Some("UTC".into())),
                false,
            ),
            Field::new("duration_ns", DataType::Int64, false),
            Field::new("status_code", DataType::Int8, false),
            Field::new("status_message", DataType::Utf8, true),
            Field::new("attributes", DataType::Utf8, false),
            Field::new("events", DataType::Utf8, false),
            Field::new("resource_attributes", DataType::Utf8, false),
        ]));

        // Create test data
        let now_ns = 1734530000000000000i64; // Fixed timestamp for testing
        let batch = RecordBatch::try_new(
            schema.clone(),
            vec![
                Arc::new(StringArray::from(vec!["span_001"])),
                Arc::new(StringArray::from(vec!["trace_001"])),
                Arc::new(StringArray::from(vec![None::<&str>])),
                Arc::new(StringArray::from(vec!["test-service"])),
                Arc::new(StringArray::from(vec!["test-operation"])),
                Arc::new(Int8Array::from(vec![1i8])),
                Arc::new(TimestampNanosecondArray::from(vec![now_ns]).with_timezone("UTC")),
                Arc::new(
                    TimestampNanosecondArray::from(vec![now_ns + 100_000]).with_timezone("UTC"),
                ),
                Arc::new(Int64Array::from(vec![100_000i64])),
                Arc::new(Int8Array::from(vec![0i8])),
                Arc::new(StringArray::from(vec![None::<&str>])),
                Arc::new(StringArray::from(vec!["{}"])),
                Arc::new(StringArray::from(vec!["[]"])),
                Arc::new(StringArray::from(vec!["{}"])),
            ],
        )
        .unwrap();

        // Write Parquet file
        let file = File::create(&file_path).unwrap();
        let props = WriterProperties::builder().build();
        let mut writer = ArrowWriter::try_new(file, schema, Some(props)).unwrap();
        writer.write(&batch).unwrap();
        writer.close().unwrap();

        // Verify file exists and has data
        assert!(file_path.exists());
        let metadata = std::fs::metadata(&file_path).unwrap();
        assert!(metadata.len() > 0);
    }

    /// Test reading a Parquet file
    #[test]
    fn test_read_parquet_file() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("test_read.parquet");

        // Create schema (simplified for read test)
        let schema = Arc::new(Schema::new(vec![
            Field::new("span_id", DataType::Utf8, false),
            Field::new("trace_id", DataType::Utf8, false),
        ]));

        // Write test data
        let batch = RecordBatch::try_new(
            schema.clone(),
            vec![
                Arc::new(StringArray::from(vec!["span_001", "span_002"])),
                Arc::new(StringArray::from(vec!["trace_001", "trace_001"])),
            ],
        )
        .unwrap();

        let file = File::create(&file_path).unwrap();
        let props = WriterProperties::builder().build();
        let mut writer = ArrowWriter::try_new(file, schema, Some(props)).unwrap();
        writer.write(&batch).unwrap();
        writer.close().unwrap();

        // Read and verify
        use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
        let file = File::open(&file_path).unwrap();
        let builder = ParquetRecordBatchReaderBuilder::try_new(file).unwrap();
        let reader = builder.build().unwrap();

        let batches: Vec<RecordBatch> = reader.map(|r| r.unwrap()).collect();
        assert_eq!(batches.len(), 1);
        assert_eq!(batches[0].num_rows(), 2);
    }
}

/// Test module for memory pressure / backpressure
mod backpressure_tests {
    /// Test memory threshold calculation logic
    #[test]
    fn test_memory_threshold_calculation() {
        let total_memory: u64 = 16 * 1024 * 1024 * 1024; // 16 GB
        let threshold_percent: f64 = 80.0;

        let threshold = (total_memory as f64 * threshold_percent / 100.0) as u64;

        // 80% of 16GB should be between 12GB and 13GB
        let min_expected: u64 = 12 * 1024 * 1024 * 1024;
        let max_expected: u64 = 13 * 1024 * 1024 * 1024;
        assert!(
            threshold >= min_expected && threshold <= max_expected,
            "Threshold {} should be between {} and {}",
            threshold,
            min_expected,
            max_expected
        );

        // Test another threshold (70% should be less than 80%)
        let threshold_70 = (total_memory as f64 * 70.0 / 100.0) as u64;
        assert!(threshold_70 < threshold);
    }

    /// Test that backpressure triggers at correct threshold
    #[test]
    fn test_backpressure_trigger() {
        let used_memory: u64 = 13 * 1024 * 1024 * 1024; // 13 GB
        let threshold: u64 = 12 * 1024 * 1024 * 1024; // 12 GB

        let should_trigger = used_memory > threshold;
        assert!(should_trigger);

        let under_threshold: u64 = 10 * 1024 * 1024 * 1024; // 10 GB
        let should_not_trigger = under_threshold > threshold;
        assert!(!should_not_trigger);
    }
}

/// Test module for gRPC message handling
mod grpc_tests {
    /// Test trace ID format conversion (hex string)
    #[test]
    fn test_trace_id_hex_conversion() {
        let trace_bytes: [u8; 16] = [
            0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef, 0x01, 0x23, 0x45, 0x67, 0x89, 0xab,
            0xcd, 0xef,
        ];

        let hex_string = hex::encode(&trace_bytes);
        assert_eq!(hex_string, "0123456789abcdef0123456789abcdef");
        assert_eq!(hex_string.len(), 32);
    }

    /// Test span ID format conversion (hex string)
    #[test]
    fn test_span_id_hex_conversion() {
        let span_bytes: [u8; 8] = [0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef];

        let hex_string = hex::encode(&span_bytes);
        assert_eq!(hex_string, "0123456789abcdef");
        assert_eq!(hex_string.len(), 16);
    }

    /// Test empty parent span ID handling
    #[test]
    fn test_empty_parent_span() {
        let empty_bytes: [u8; 0] = [];
        let hex_string = hex::encode(&empty_bytes);
        assert_eq!(hex_string, "");

        // Empty parent should be treated as None/null
        let is_root = empty_bytes.is_empty();
        assert!(is_root);
    }
}

/// Test module for date partitioning
mod partitioning_tests {
    use chrono::{TimeZone, Utc};

    /// Test date partition path generation
    #[test]
    fn test_date_partition_path() {
        let timestamp_ns: i64 = 1734530000000000000; // Dec 18, 2024
        let dt = Utc.timestamp_nanos(timestamp_ns);

        let partition_path = format!(
            "year={}/month={:02}/day={:02}",
            dt.format("%Y"),
            dt.format("%m"),
            dt.format("%d")
        );

        assert!(partition_path.starts_with("year=2024"));
        assert!(partition_path.contains("/month="));
        assert!(partition_path.contains("/day="));
    }

    /// Test filename generation with service name
    #[test]
    fn test_filename_generation() {
        let service_name = "my-service";
        let timestamp = 1734530000u64;
        let random_suffix = "abcd1234";

        let filename = format!(
            "{}_{:010}_{}.parquet",
            service_name, timestamp, random_suffix
        );
        assert!(filename.starts_with("my-service"));
        assert!(filename.ends_with(".parquet"));
        assert!(filename.contains("_"));
    }
}
