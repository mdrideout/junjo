package storage

import (
	"bytes"
	"fmt"

	"github.com/apache/arrow/go/v18/arrow"
	"github.com/apache/arrow/go/v18/arrow/ipc"
	"github.com/apache/arrow/go/v18/arrow/memory"
)

// BuildRecordBatch creates an Arrow record batch from span records.
// Exported version of buildRecordBatch for use by gRPC handlers.
func BuildRecordBatch(alloc memory.Allocator, records []SpanRecord) (arrow.Record, error) {
	return buildRecordBatch(alloc, records)
}

// SerializeRecordBatchToIPC converts an Arrow RecordBatch to IPC stream bytes.
// The IPC stream format includes the schema, making it self-describing.
func SerializeRecordBatchToIPC(batch arrow.Record) ([]byte, error) {
	var buf bytes.Buffer

	// Create IPC writer with the batch's schema
	writer := ipc.NewWriter(&buf, ipc.WithSchema(batch.Schema()))

	// Write the record batch
	if err := writer.Write(batch); err != nil {
		writer.Close()
		return nil, fmt.Errorf("failed to write record batch to IPC: %w", err)
	}

	// Close the writer to flush any remaining data
	if err := writer.Close(); err != nil {
		return nil, fmt.Errorf("failed to close IPC writer: %w", err)
	}

	return buf.Bytes(), nil
}

// SpanRecordsToIPCBytes converts span records directly to Arrow IPC bytes.
// This is a convenience function combining BuildRecordBatch and SerializeRecordBatchToIPC.
func SpanRecordsToIPCBytes(records []SpanRecord) ([]byte, error) {
	if len(records) == 0 {
		// Return empty IPC stream with schema only
		return serializeEmptyBatch()
	}

	alloc := memory.NewGoAllocator()
	batch, err := BuildRecordBatch(alloc, records)
	if err != nil {
		return nil, fmt.Errorf("failed to build record batch: %w", err)
	}
	defer batch.Release()

	return SerializeRecordBatchToIPC(batch)
}

// serializeEmptyBatch creates an IPC stream with schema but no data rows.
// This allows the client to know the schema even when there's no data.
func serializeEmptyBatch() ([]byte, error) {
	var buf bytes.Buffer

	// Create IPC writer with the span schema
	writer := ipc.NewWriter(&buf, ipc.WithSchema(SpanSchema))

	// Close without writing any batches - this writes just the schema
	if err := writer.Close(); err != nil {
		return nil, fmt.Errorf("failed to close empty IPC writer: %w", err)
	}

	return buf.Bytes(), nil
}
