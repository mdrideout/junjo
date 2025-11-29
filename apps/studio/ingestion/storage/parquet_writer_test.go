package storage

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/apache/arrow/go/v18/parquet/file"
	"github.com/apache/arrow/go/v18/parquet/pqarrow"
)

func TestWriteSpansToParquet(t *testing.T) {
	// Create temp directory
	tmpDir, err := os.MkdirTemp("", "parquet-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	// Create test records
	parentSpanID := "abcd1234abcd1234"
	statusMsg := "OK"
	records := []SpanRecord{
		{
			SpanID:             "1234567890abcdef",
			TraceID:            "abcdef1234567890",
			ParentSpanID:       nil, // root span
			ServiceName:        "test-service",
			Name:               "test-operation",
			SpanKind:           1, // Server
			StartTimeNanos:     1700000000000000000,
			EndTimeNanos:       1700000001000000000,
			DurationNanos:      1000000000,
			StatusCode:         1, // OK
			StatusMessage:      &statusMsg,
			Attributes:         `{"http.method":"GET","http.url":"/api/test"}`,
			Events:             `[]`,
			ResourceAttributes: `{"service.name":"test-service","service.version":"1.0.0"}`,
		},
		{
			SpanID:             "fedcba0987654321",
			TraceID:            "abcdef1234567890",
			ParentSpanID:       &parentSpanID,
			ServiceName:        "test-service",
			Name:               "child-operation",
			SpanKind:           0, // Internal
			StartTimeNanos:     1700000000100000000,
			EndTimeNanos:       1700000000900000000,
			DurationNanos:      800000000,
			StatusCode:         0, // Unset
			StatusMessage:      nil,
			Attributes:         `{}`,
			Events:             `[{"name":"event1","timestamp":1700000000500000000}]`,
			ResourceAttributes: `{"service.name":"test-service"}`,
		},
	}

	// Write to Parquet
	outputPath := filepath.Join(tmpDir, "spans", "year=2024", "month=01", "day=15", "test-service_1700000000_abcd1234.parquet")
	config := DefaultParquetWriterConfig()

	if err := WriteSpansToParquet(records, outputPath, config); err != nil {
		t.Fatalf("WriteSpansToParquet failed: %v", err)
	}

	// Verify file exists
	if _, err := os.Stat(outputPath); os.IsNotExist(err) {
		t.Fatalf("Parquet file was not created")
	}

	// Read back and verify
	reader, err := file.OpenParquetFile(outputPath, false)
	if err != nil {
		t.Fatalf("Failed to open parquet file: %v", err)
	}
	defer reader.Close()

	// Check row count
	numRows := reader.NumRows()
	if numRows != 2 {
		t.Errorf("Expected 2 rows, got %d", numRows)
	}

	// Read with Arrow
	arrowReader, err := pqarrow.NewFileReader(reader, pqarrow.ArrowReadProperties{}, nil)
	if err != nil {
		t.Fatalf("Failed to create arrow reader: %v", err)
	}

	table, err := arrowReader.ReadTable(context.Background())
	if err != nil {
		t.Fatalf("Failed to read table: %v", err)
	}
	defer table.Release()

	// Verify schema
	schema := table.Schema()
	if schema.NumFields() != 14 {
		t.Errorf("Expected 14 fields, got %d", schema.NumFields())
	}

	// Verify some field names
	expectedFields := []string{"span_id", "trace_id", "service_name", "name", "start_time"}
	for _, fieldName := range expectedFields {
		indices := schema.FieldIndices(fieldName)
		if len(indices) == 0 {
			t.Errorf("Missing field: %s", fieldName)
		}
	}

	// Verify row count in table
	if table.NumRows() != 2 {
		t.Errorf("Table has %d rows, expected 2", table.NumRows())
	}
}

func TestWriteSpansToParquetEmptyRecords(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "parquet-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	outputPath := filepath.Join(tmpDir, "empty.parquet")
	config := DefaultParquetWriterConfig()

	err = WriteSpansToParquet([]SpanRecord{}, outputPath, config)
	if err == nil {
		t.Error("Expected error for empty records, got nil")
	}
}

func TestWriteSpansToParquetCreatesDirectory(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "parquet-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	// Path with non-existent nested directories
	outputPath := filepath.Join(tmpDir, "a", "b", "c", "test.parquet")
	config := DefaultParquetWriterConfig()

	records := []SpanRecord{
		{
			SpanID:             "1234567890abcdef",
			TraceID:            "abcdef1234567890",
			ServiceName:        "test-service",
			Name:               "test-operation",
			SpanKind:           1,
			StartTimeNanos:     1700000000000000000,
			EndTimeNanos:       1700000001000000000,
			DurationNanos:      1000000000,
			StatusCode:         1,
			Attributes:         `{}`,
			Events:             `[]`,
			ResourceAttributes: `{}`,
		},
	}

	if err := WriteSpansToParquet(records, outputPath, config); err != nil {
		t.Fatalf("WriteSpansToParquet failed: %v", err)
	}

	if _, err := os.Stat(outputPath); os.IsNotExist(err) {
		t.Error("Expected file to be created in nested directory")
	}
}
