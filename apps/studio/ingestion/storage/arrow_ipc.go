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

	// Close to flush
	if err := writer.Close(); err != nil {
		return nil, fmt.Errorf("failed to close IPC writer: %w", err)
	}

	return buf.Bytes(), nil
}

// SpanRecordsToIPCBytes converts span records to Arrow IPC stream bytes.
// This is a convenience function combining BuildRecordBatch and SerializeRecordBatchToIPC.
func SpanRecordsToIPCBytes(records []SpanRecord) ([]byte, error) {
	if len(records) == 0 {
		// Return empty IPC stream for empty records
		return []byte{}, nil
	}

	alloc := memory.NewGoAllocator()
	batch, err := BuildRecordBatch(alloc, records)
	if err != nil {
		return nil, fmt.Errorf("failed to build record batch: %w", err)
	}
	defer batch.Release()

	return SerializeRecordBatchToIPC(batch)
}
