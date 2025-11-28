package storage

import (
	"os"
	"testing"

	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

func TestReadSpansSkipsCounterKey(t *testing.T) {
	// Create temp directory for test DB
	dir, err := os.MkdirTemp("", "badger-test-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Initialize storage (this creates __span_count__ key)
	store, err := NewStorage(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()

	// Write a test span
	span := &tracepb.Span{
		TraceId: []byte("test-trace-id-1234"),
		SpanId:  []byte("test-span"),
		Name:    "test-operation",
	}
	resource := &resourcepb.Resource{}

	if err := store.WriteSpan(span, resource); err != nil {
		t.Fatal(err)
	}

	// Read spans - should get 1 span, NOT the counter key
	var readCount int
	var lastKey []byte
	sendFunc := func(key, spanBytes, resourceBytes []byte) error {
		readCount++
		lastKey = key
		// Verify key is NOT the counter key
		if string(key) == CounterKey {
			t.Error("ReadSpans returned the counter key as a span!")
		}
		return nil
	}

	processedKey, corrupted, err := store.ReadSpans(nil, 100, sendFunc)
	if err != nil {
		t.Fatal(err)
	}

	// Verify results
	if readCount != 1 {
		t.Errorf("Expected 1 span, got %d", readCount)
	}
	if corrupted != 0 {
		t.Errorf("Expected 0 corrupted, got %d", corrupted)
	}
	if string(processedKey) == CounterKey {
		t.Error("lastKeyProcessed should not be the counter key")
	}
	if string(lastKey) == CounterKey {
		t.Error("Sent key should not be the counter key")
	}
}

func TestReadSpansWithOnlyCounterKey(t *testing.T) {
	// Test edge case: DB has counter but no spans
	dir, err := os.MkdirTemp("", "badger-test-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	store, err := NewStorage(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()

	// Don't write any spans - only counter exists from init

	var readCount int
	sendFunc := func(key, spanBytes, resourceBytes []byte) error {
		readCount++
		if string(key) == CounterKey {
			t.Error("ReadSpans returned counter key!")
		}
		return nil
	}

	lastKey, corrupted, err := store.ReadSpans(nil, 100, sendFunc)
	if err != nil {
		t.Fatal(err)
	}

	if readCount != 0 {
		t.Errorf("Expected 0 spans, got %d", readCount)
	}
	if corrupted != 0 {
		t.Errorf("Expected 0 corrupted, got %d", corrupted)
	}
	// lastKey should be nil or empty when no spans exist
	if len(lastKey) > 0 && string(lastKey) == CounterKey {
		t.Error("lastKeyProcessed should not be counter key")
	}
}
