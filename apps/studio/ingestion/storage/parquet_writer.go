package storage

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/apache/arrow/go/v18/arrow"
	"github.com/apache/arrow/go/v18/arrow/array"
	"github.com/apache/arrow/go/v18/arrow/memory"
	"github.com/apache/arrow/go/v18/parquet"
	"github.com/apache/arrow/go/v18/parquet/compress"
	"github.com/apache/arrow/go/v18/parquet/pqarrow"
)

// TimestampNsUTC is a nanosecond timestamp with UTC timezone.
var TimestampNsUTC = &arrow.TimestampType{Unit: arrow.Nanosecond, TimeZone: "UTC"}

// SpanSchema defines the Arrow schema for span data in Parquet files.
// This matches the V4 architecture specification.
var SpanSchema = arrow.NewSchema(
	[]arrow.Field{
		{Name: "span_id", Type: arrow.BinaryTypes.String, Nullable: false},
		{Name: "trace_id", Type: arrow.BinaryTypes.String, Nullable: false},
		{Name: "parent_span_id", Type: arrow.BinaryTypes.String, Nullable: true},
		{Name: "service_name", Type: arrow.BinaryTypes.String, Nullable: false},
		{Name: "name", Type: arrow.BinaryTypes.String, Nullable: false},
		{Name: "span_kind", Type: arrow.PrimitiveTypes.Int8, Nullable: false},
		{Name: "start_time", Type: TimestampNsUTC, Nullable: false},
		{Name: "end_time", Type: TimestampNsUTC, Nullable: false},
		{Name: "duration_ns", Type: arrow.PrimitiveTypes.Int64, Nullable: false},
		{Name: "status_code", Type: arrow.PrimitiveTypes.Int8, Nullable: false},
		{Name: "status_message", Type: arrow.BinaryTypes.String, Nullable: true},
		{Name: "attributes", Type: arrow.BinaryTypes.String, Nullable: false},         // JSON string
		{Name: "events", Type: arrow.BinaryTypes.String, Nullable: false},              // JSON string
		{Name: "resource_attributes", Type: arrow.BinaryTypes.String, Nullable: false}, // JSON string
	},
	nil,
)

// SpanRecord represents a single span ready for Parquet writing.
// All fields are already converted to their final types.
type SpanRecord struct {
	SpanID             string
	TraceID            string
	ParentSpanID       *string // nil if no parent
	ServiceName        string
	Name               string
	SpanKind           int8
	StartTimeNanos     int64
	EndTimeNanos       int64
	DurationNanos      int64
	StatusCode         int8
	StatusMessage      *string // nil if no message
	Attributes         string  // JSON
	Events             string  // JSON
	ResourceAttributes string  // JSON
}

// ParquetWriterConfig holds configuration for Parquet file writing.
type ParquetWriterConfig struct {
	RowGroupSize     int64
	CompressionCodec compress.Compression
	CompressionLevel int
}

// DefaultParquetWriterConfig returns the default configuration per V4 architecture.
func DefaultParquetWriterConfig() ParquetWriterConfig {
	return ParquetWriterConfig{
		RowGroupSize:     122880, // Optimal for DataFusion
		CompressionCodec: compress.Codecs.Zstd,
		CompressionLevel: 3,
	}
}

// WriteSpansToParquet writes span records to a Parquet file.
// The outputPath directory will be created if it doesn't exist.
func WriteSpansToParquet(records []SpanRecord, outputPath string, config ParquetWriterConfig) error {
	if len(records) == 0 {
		return fmt.Errorf("no records to write")
	}

	// Ensure directory exists
	dir := filepath.Dir(outputPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("failed to create directory %s: %w", dir, err)
	}

	// Create file
	file, err := os.Create(outputPath)
	if err != nil {
		return fmt.Errorf("failed to create file %s: %w", outputPath, err)
	}
	defer file.Close()

	// Build Arrow record batch
	alloc := memory.NewGoAllocator()
	batch, err := buildRecordBatch(alloc, records)
	if err != nil {
		return fmt.Errorf("failed to build record batch: %w", err)
	}
	defer batch.Release()

	// Configure Parquet writer
	writerProps := parquet.NewWriterProperties(
		parquet.WithCompression(config.CompressionCodec),
		parquet.WithCompressionLevel(config.CompressionLevel),
	)
	arrowProps := pqarrow.NewArrowWriterProperties(
		pqarrow.WithStoreSchema(),
	)

	// Write to file
	writer, err := pqarrow.NewFileWriter(SpanSchema, file, writerProps, arrowProps)
	if err != nil {
		return fmt.Errorf("failed to create parquet writer: %w", err)
	}

	if err := writer.WriteBuffered(batch); err != nil {
		writer.Close()
		return fmt.Errorf("failed to write record batch: %w", err)
	}

	if err := writer.Close(); err != nil {
		return fmt.Errorf("failed to close parquet writer: %w", err)
	}

	return nil
}

// buildRecordBatch creates an Arrow record batch from span records.
func buildRecordBatch(alloc memory.Allocator, records []SpanRecord) (arrow.Record, error) {
	// Create builders for each column
	spanIDBuilder := array.NewStringBuilder(alloc)
	defer spanIDBuilder.Release()

	traceIDBuilder := array.NewStringBuilder(alloc)
	defer traceIDBuilder.Release()

	parentSpanIDBuilder := array.NewStringBuilder(alloc)
	defer parentSpanIDBuilder.Release()

	serviceNameBuilder := array.NewStringBuilder(alloc)
	defer serviceNameBuilder.Release()

	nameBuilder := array.NewStringBuilder(alloc)
	defer nameBuilder.Release()

	spanKindBuilder := array.NewInt8Builder(alloc)
	defer spanKindBuilder.Release()

	startTimeBuilder := array.NewTimestampBuilder(alloc, TimestampNsUTC)
	defer startTimeBuilder.Release()

	endTimeBuilder := array.NewTimestampBuilder(alloc, TimestampNsUTC)
	defer endTimeBuilder.Release()

	durationBuilder := array.NewInt64Builder(alloc)
	defer durationBuilder.Release()

	statusCodeBuilder := array.NewInt8Builder(alloc)
	defer statusCodeBuilder.Release()

	statusMessageBuilder := array.NewStringBuilder(alloc)
	defer statusMessageBuilder.Release()

	attributesBuilder := array.NewStringBuilder(alloc)
	defer attributesBuilder.Release()

	eventsBuilder := array.NewStringBuilder(alloc)
	defer eventsBuilder.Release()

	resourceAttributesBuilder := array.NewStringBuilder(alloc)
	defer resourceAttributesBuilder.Release()

	// Append records
	for _, r := range records {
		spanIDBuilder.Append(r.SpanID)
		traceIDBuilder.Append(r.TraceID)

		if r.ParentSpanID != nil {
			parentSpanIDBuilder.Append(*r.ParentSpanID)
		} else {
			parentSpanIDBuilder.AppendNull()
		}

		serviceNameBuilder.Append(r.ServiceName)
		nameBuilder.Append(r.Name)
		spanKindBuilder.Append(r.SpanKind)
		startTimeBuilder.Append(arrow.Timestamp(r.StartTimeNanos))
		endTimeBuilder.Append(arrow.Timestamp(r.EndTimeNanos))
		durationBuilder.Append(r.DurationNanos)
		statusCodeBuilder.Append(r.StatusCode)

		if r.StatusMessage != nil {
			statusMessageBuilder.Append(*r.StatusMessage)
		} else {
			statusMessageBuilder.AppendNull()
		}

		attributesBuilder.Append(r.Attributes)
		eventsBuilder.Append(r.Events)
		resourceAttributesBuilder.Append(r.ResourceAttributes)
	}

	// Build arrays
	cols := []arrow.Array{
		spanIDBuilder.NewArray(),
		traceIDBuilder.NewArray(),
		parentSpanIDBuilder.NewArray(),
		serviceNameBuilder.NewArray(),
		nameBuilder.NewArray(),
		spanKindBuilder.NewArray(),
		startTimeBuilder.NewArray(),
		endTimeBuilder.NewArray(),
		durationBuilder.NewArray(),
		statusCodeBuilder.NewArray(),
		statusMessageBuilder.NewArray(),
		attributesBuilder.NewArray(),
		eventsBuilder.NewArray(),
		resourceAttributesBuilder.NewArray(),
	}

	// Create record batch
	return array.NewRecord(SpanSchema, cols, int64(len(records))), nil
}
