package storage

import (
	"os"
	"path/filepath"
	"sync"
	"testing"

	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

func setupTestStorage(t *testing.T) (*Storage, func()) {
	t.Helper()
	dir, err := os.MkdirTemp("", "sqlite-test-*")
	if err != nil {
		t.Fatal(err)
	}

	dbPath := filepath.Join(dir, "test.db")
	store, err := NewStorage(dbPath)
	if err != nil {
		os.RemoveAll(dir)
		t.Fatal(err)
	}

	cleanup := func() {
		store.Close()
		os.RemoveAll(dir)
	}

	return store, cleanup
}

func createTestSpan(traceID, spanID, name string) (*tracepb.Span, *resourcepb.Resource) {
	span := &tracepb.Span{
		TraceId: []byte(traceID),
		SpanId:  []byte(spanID),
		Name:    name,
	}
	resource := &resourcepb.Resource{}
	return span, resource
}

func TestWriteAndReadSpan(t *testing.T) {
	store, cleanup := setupTestStorage(t)
	defer cleanup()

	span, resource := createTestSpan("test-trace-id-1234", "test-span-id", "test-operation")

	if err := store.WriteSpan(span, resource); err != nil {
		t.Fatalf("WriteSpan failed: %v", err)
	}

	// Read the span back
	var readCount int
	var lastKey []byte
	sendFunc := func(key, spanBytes, resourceBytes []byte) error {
		readCount++
		lastKey = key
		return nil
	}

	processedKey, corrupted, err := store.ReadSpans(nil, 100, sendFunc)
	if err != nil {
		t.Fatalf("ReadSpans failed: %v", err)
	}

	if readCount != 1 {
		t.Errorf("Expected 1 span, got %d", readCount)
	}
	if corrupted != 0 {
		t.Errorf("Expected 0 corrupted, got %d", corrupted)
	}
	if len(processedKey) == 0 {
		t.Error("Expected non-empty lastKeyProcessed")
	}
	if len(lastKey) == 0 {
		t.Error("Expected non-empty lastKey from sendFunc")
	}
}

func TestReadSpansEmpty(t *testing.T) {
	store, cleanup := setupTestStorage(t)
	defer cleanup()

	var readCount int
	sendFunc := func(key, spanBytes, resourceBytes []byte) error {
		readCount++
		return nil
	}

	lastKey, corrupted, err := store.ReadSpans(nil, 100, sendFunc)
	if err != nil {
		t.Fatalf("ReadSpans failed: %v", err)
	}

	if readCount != 0 {
		t.Errorf("Expected 0 spans, got %d", readCount)
	}
	if corrupted != 0 {
		t.Errorf("Expected 0 corrupted, got %d", corrupted)
	}
	if len(lastKey) > 0 {
		t.Errorf("Expected empty lastKey, got %x", lastKey)
	}
}

func TestReadSpansPagination(t *testing.T) {
	store, cleanup := setupTestStorage(t)
	defer cleanup()

	// Write 10 spans
	for i := 0; i < 10; i++ {
		span, resource := createTestSpan("trace", "span", "op")
		if err := store.WriteSpan(span, resource); err != nil {
			t.Fatalf("WriteSpan failed: %v", err)
		}
	}

	// Read first batch of 3
	var keys [][]byte
	sendFunc := func(key, spanBytes, resourceBytes []byte) error {
		keys = append(keys, append([]byte(nil), key...))
		return nil
	}

	lastKey, _, err := store.ReadSpans(nil, 3, sendFunc)
	if err != nil {
		t.Fatalf("ReadSpans failed: %v", err)
	}

	if len(keys) != 3 {
		t.Errorf("Expected 3 spans in first batch, got %d", len(keys))
	}

	// Read second batch starting after lastKey
	keys = nil
	lastKey2, _, err := store.ReadSpans(lastKey, 3, sendFunc)
	if err != nil {
		t.Fatalf("ReadSpans failed: %v", err)
	}

	if len(keys) != 3 {
		t.Errorf("Expected 3 spans in second batch, got %d", len(keys))
	}

	// Keys should be different from first batch
	if string(lastKey2) == string(lastKey) {
		t.Error("Second batch should have different lastKey than first")
	}

	// Read remaining 4
	keys = nil
	_, _, err = store.ReadSpans(lastKey2, 10, sendFunc)
	if err != nil {
		t.Fatalf("ReadSpans failed: %v", err)
	}

	if len(keys) != 4 {
		t.Errorf("Expected 4 spans in final batch, got %d", len(keys))
	}
}

func TestMonotonicULIDOrdering(t *testing.T) {
	store, cleanup := setupTestStorage(t)
	defer cleanup()

	// Write multiple spans quickly
	for i := 0; i < 100; i++ {
		span, resource := createTestSpan("trace", "span", "op")
		if err := store.WriteSpan(span, resource); err != nil {
			t.Fatalf("WriteSpan failed: %v", err)
		}
	}

	// Read all spans and verify keys are monotonically increasing
	var keys [][]byte
	sendFunc := func(key, spanBytes, resourceBytes []byte) error {
		keys = append(keys, append([]byte(nil), key...))
		return nil
	}

	_, _, err := store.ReadSpans(nil, 100, sendFunc)
	if err != nil {
		t.Fatalf("ReadSpans failed: %v", err)
	}

	if len(keys) != 100 {
		t.Errorf("Expected 100 spans, got %d", len(keys))
	}

	// Verify ordering
	for i := 1; i < len(keys); i++ {
		if string(keys[i]) <= string(keys[i-1]) {
			t.Errorf("Keys not monotonically increasing at index %d", i)
		}
	}
}

func TestCounterOperations(t *testing.T) {
	store, cleanup := setupTestStorage(t)
	defer cleanup()

	// Initial count should be 0
	count, err := store.GetUnretrievedCount()
	if err != nil {
		t.Fatalf("GetUnretrievedCount failed: %v", err)
	}
	if count != 0 {
		t.Errorf("Expected initial count 0, got %d", count)
	}

	// Write 5 spans - count should increase
	for i := 0; i < 5; i++ {
		span, resource := createTestSpan("trace", "span", "op")
		if err := store.WriteSpan(span, resource); err != nil {
			t.Fatalf("WriteSpan failed: %v", err)
		}
	}

	count, err = store.GetUnretrievedCount()
	if err != nil {
		t.Fatalf("GetUnretrievedCount failed: %v", err)
	}
	if count != 5 {
		t.Errorf("Expected count 5, got %d", count)
	}

	// Decrement by 3
	remaining, err := store.DecrementAndGetCount(3)
	if err != nil {
		t.Fatalf("DecrementAndGetCount failed: %v", err)
	}
	if remaining != 2 {
		t.Errorf("Expected remaining 2, got %d", remaining)
	}

	// Verify count
	count, err = store.GetUnretrievedCount()
	if err != nil {
		t.Fatalf("GetUnretrievedCount failed: %v", err)
	}
	if count != 2 {
		t.Errorf("Expected count 2, got %d", count)
	}
}

func TestCounterUnderflowProtection(t *testing.T) {
	store, cleanup := setupTestStorage(t)
	defer cleanup()

	// Write 2 spans
	for i := 0; i < 2; i++ {
		span, resource := createTestSpan("trace", "span", "op")
		if err := store.WriteSpan(span, resource); err != nil {
			t.Fatalf("WriteSpan failed: %v", err)
		}
	}

	// Try to decrement by 10 (more than available)
	remaining, err := store.DecrementAndGetCount(10)
	if err != nil {
		t.Fatalf("DecrementAndGetCount failed: %v", err)
	}

	// Should floor at 0, not wrap around
	if remaining != 0 {
		t.Errorf("Expected remaining 0 (underflow protection), got %d", remaining)
	}
}

func TestReconcileCount(t *testing.T) {
	store, cleanup := setupTestStorage(t)
	defer cleanup()

	// Write some spans
	for i := 0; i < 5; i++ {
		span, resource := createTestSpan("trace", "span", "op")
		if err := store.WriteSpan(span, resource); err != nil {
			t.Fatalf("WriteSpan failed: %v", err)
		}
	}

	// Verify count matches
	count, err := store.GetUnretrievedCount()
	if err != nil {
		t.Fatalf("GetUnretrievedCount failed: %v", err)
	}
	if count != 5 {
		t.Errorf("Expected count 5, got %d", count)
	}

	// Run reconciliation (should find no drift)
	if err := store.ReconcileCount(); err != nil {
		t.Fatalf("ReconcileCount failed: %v", err)
	}

	// Count should still be 5
	count, err = store.GetUnretrievedCount()
	if err != nil {
		t.Fatalf("GetUnretrievedCount failed: %v", err)
	}
	if count != 5 {
		t.Errorf("Expected count 5 after reconcile, got %d", count)
	}
}

func TestConcurrentWrites(t *testing.T) {
	store, cleanup := setupTestStorage(t)
	defer cleanup()

	// Write 100 spans concurrently from 10 goroutines
	var wg sync.WaitGroup
	numGoroutines := 10
	spansPerGoroutine := 10

	for g := 0; g < numGoroutines; g++ {
		wg.Add(1)
		go func(goroutineID int) {
			defer wg.Done()
			for i := 0; i < spansPerGoroutine; i++ {
				span, resource := createTestSpan("trace", "span", "op")
				if err := store.WriteSpan(span, resource); err != nil {
					t.Errorf("WriteSpan failed in goroutine %d: %v", goroutineID, err)
					return
				}
			}
		}(g)
	}

	wg.Wait()

	// Verify all spans were written
	var readCount int
	sendFunc := func(key, spanBytes, resourceBytes []byte) error {
		readCount++
		return nil
	}

	_, _, err := store.ReadSpans(nil, 1000, sendFunc)
	if err != nil {
		t.Fatalf("ReadSpans failed: %v", err)
	}

	expectedCount := numGoroutines * spansPerGoroutine
	if readCount != expectedCount {
		t.Errorf("Expected %d spans, got %d", expectedCount, readCount)
	}

	// Verify counter matches
	count, err := store.GetUnretrievedCount()
	if err != nil {
		t.Fatalf("GetUnretrievedCount failed: %v", err)
	}
	if count != uint64(expectedCount) {
		t.Errorf("Expected counter %d, got %d", expectedCount, count)
	}
}

func TestCloseAndReopen(t *testing.T) {
	dir, err := os.MkdirTemp("", "sqlite-test-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	dbPath := filepath.Join(dir, "test.db")

	// Create storage and write spans
	store, err := NewStorage(dbPath)
	if err != nil {
		t.Fatalf("NewStorage failed: %v", err)
	}

	for i := 0; i < 5; i++ {
		span, resource := createTestSpan("trace", "span", "op")
		if err := store.WriteSpan(span, resource); err != nil {
			t.Fatalf("WriteSpan failed: %v", err)
		}
	}

	// Close
	if err := store.Close(); err != nil {
		t.Fatalf("Close failed: %v", err)
	}

	// Reopen
	store, err = NewStorage(dbPath)
	if err != nil {
		t.Fatalf("NewStorage (reopen) failed: %v", err)
	}
	defer store.Close()

	// Verify data persisted
	var readCount int
	sendFunc := func(key, spanBytes, resourceBytes []byte) error {
		readCount++
		return nil
	}

	_, _, err = store.ReadSpans(nil, 100, sendFunc)
	if err != nil {
		t.Fatalf("ReadSpans failed: %v", err)
	}

	if readCount != 5 {
		t.Errorf("Expected 5 spans after reopen, got %d", readCount)
	}

	// Counter should also persist
	count, err := store.GetUnretrievedCount()
	if err != nil {
		t.Fatalf("GetUnretrievedCount failed: %v", err)
	}
	if count != 5 {
		t.Errorf("Expected counter 5 after reopen, got %d", count)
	}
}

func TestFlushStateOperations(t *testing.T) {
	store, cleanup := setupTestStorage(t)
	defer cleanup()

	// Initial flush state should have zero values
	state, err := store.GetFlushState()
	if err != nil {
		t.Fatalf("GetFlushState failed: %v", err)
	}
	if !state.LastFlushTime.IsZero() && state.LastFlushTime.Unix() != 0 {
		t.Errorf("Expected zero LastFlushTime, got %v", state.LastFlushTime)
	}
	if state.FirstFlushedKey != nil {
		t.Errorf("Expected nil FirstFlushedKey, got %x", state.FirstFlushedKey)
	}
	if state.LastFlushedKey != nil {
		t.Errorf("Expected nil LastFlushedKey, got %x", state.LastFlushedKey)
	}
	if state.TotalFlushedRows != 0 {
		t.Errorf("Expected 0 TotalFlushedRows, got %d", state.TotalFlushedRows)
	}

	// Update flush state
	firstKey := []byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10}
	lastKey := []byte{0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20}

	if err := store.UpdateFlushState(firstKey, lastKey, 100); err != nil {
		t.Fatalf("UpdateFlushState failed: %v", err)
	}

	// Verify updated state
	state, err = store.GetFlushState()
	if err != nil {
		t.Fatalf("GetFlushState failed: %v", err)
	}
	if state.LastFlushTime.Unix() == 0 {
		t.Error("Expected non-zero LastFlushTime after update")
	}
	if string(state.FirstFlushedKey) != string(firstKey) {
		t.Errorf("FirstFlushedKey mismatch: got %x, want %x", state.FirstFlushedKey, firstKey)
	}
	if string(state.LastFlushedKey) != string(lastKey) {
		t.Errorf("LastFlushedKey mismatch: got %x, want %x", state.LastFlushedKey, lastKey)
	}
	if state.TotalFlushedRows != 100 {
		t.Errorf("Expected TotalFlushedRows 100, got %d", state.TotalFlushedRows)
	}

	// Update again - total should accumulate
	newFirstKey := []byte{0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2a, 0x2b, 0x2c, 0x2d, 0x2e, 0x2f, 0x30}
	newLastKey := []byte{0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x3b, 0x3c, 0x3d, 0x3e, 0x3f, 0x40}

	if err := store.UpdateFlushState(newFirstKey, newLastKey, 50); err != nil {
		t.Fatalf("UpdateFlushState failed: %v", err)
	}

	state, err = store.GetFlushState()
	if err != nil {
		t.Fatalf("GetFlushState failed: %v", err)
	}
	if state.TotalFlushedRows != 150 {
		t.Errorf("Expected TotalFlushedRows 150 after second update, got %d", state.TotalFlushedRows)
	}
	if string(state.FirstFlushedKey) != string(newFirstKey) {
		t.Errorf("FirstFlushedKey should be updated to new key")
	}
	if string(state.LastFlushedKey) != string(newLastKey) {
		t.Errorf("LastFlushedKey should be updated to new key")
	}
}

func TestGetSpanCount(t *testing.T) {
	store, cleanup := setupTestStorage(t)
	defer cleanup()

	// Initial count should be 0
	count, err := store.GetSpanCount()
	if err != nil {
		t.Fatalf("GetSpanCount failed: %v", err)
	}
	if count != 0 {
		t.Errorf("Expected initial count 0, got %d", count)
	}

	// Write some spans
	for i := 0; i < 7; i++ {
		span, resource := createTestSpan("trace", "span", "op")
		if err := store.WriteSpan(span, resource); err != nil {
			t.Fatalf("WriteSpan failed: %v", err)
		}
	}

	// Count should be 7
	count, err = store.GetSpanCount()
	if err != nil {
		t.Fatalf("GetSpanCount failed: %v", err)
	}
	if count != 7 {
		t.Errorf("Expected count 7, got %d", count)
	}
}
