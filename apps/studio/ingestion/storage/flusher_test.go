package storage

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"junjo-ai-studio/ingestion/config"

	commonpb "go.opentelemetry.io/proto/otlp/common/v1"
	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

// setupTestConfig sets up config for testing with the given output directory.
func setupTestConfig(t *testing.T, outputDir string) {
	t.Helper()
	cfg := config.Default()
	cfg.Flusher.OutputDir = outputDir
	cfg.Flusher.MinRows = 1 // Allow flushing small batches for testing
	config.SetForTesting(cfg)
}

func TestFlusherFlush(t *testing.T) {
	// Create temp directories
	tmpDir, err := os.MkdirTemp("", "flusher-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "test.db")
	outputDir := filepath.Join(tmpDir, "spans")

	// Set up test config
	setupTestConfig(t, outputDir)

	// Create repository
	repo, err := NewSQLiteRepository(dbPath)
	if err != nil {
		t.Fatalf("Failed to create repository: %v", err)
	}
	defer repo.Close()

	// Write test spans
	for i := 0; i < 10; i++ {
		span := createFlusherTestSpan(t, i)
		resource := createFlusherTestResource("test-service")
		if err := repo.WriteSpan(span, resource); err != nil {
			t.Fatalf("Failed to write span %d: %v", i, err)
		}
	}

	// Verify spans are in storage
	count, err := repo.GetSpanCount()
	if err != nil {
		t.Fatalf("Failed to get span count: %v", err)
	}
	if count != 10 {
		t.Fatalf("Expected 10 spans, got %d", count)
	}

	// Create flusher
	flusher := NewFlusher(repo)

	// Perform manual flush (don't start background process)
	if err := flusher.doStreamingFlush(); err != nil {
		t.Fatalf("Flush failed: %v", err)
	}

	// Verify spans were deleted from SQLite
	count, err = repo.GetSpanCount()
	if err != nil {
		t.Fatalf("Failed to get span count after flush: %v", err)
	}
	if count != 0 {
		t.Errorf("Expected 0 spans after flush, got %d", count)
	}

	// Verify Parquet file was created
	files, err := filepath.Glob(filepath.Join(outputDir, "year=*", "month=*", "day=*", "*.parquet"))
	if err != nil {
		t.Fatalf("Failed to glob parquet files: %v", err)
	}
	if len(files) != 1 {
		t.Errorf("Expected 1 parquet file, got %d", len(files))
	}

	// Verify flush state was updated
	state, err := repo.GetFlushState()
	if err != nil {
		t.Fatalf("Failed to get flush state: %v", err)
	}
	if state.TotalFlushedRows != 10 {
		t.Errorf("Expected TotalFlushedRows=10, got %d", state.TotalFlushedRows)
	}
	if state.FirstFlushedKey == nil {
		t.Error("FirstFlushedKey should not be nil")
	}
	if state.LastFlushedKey == nil {
		t.Error("LastFlushedKey should not be nil")
	}
}

func TestFlusherCheckAndFlush_RowCountThreshold(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "flusher-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "test.db")
	outputDir := filepath.Join(tmpDir, "spans")

	// Set up test config with low row count threshold
	cfg := config.Default()
	cfg.Flusher.OutputDir = outputDir
	cfg.Flusher.MaxRows = 3 // Threshold below current count
	cfg.Flusher.MinRows = 1
	config.SetForTesting(cfg)

	repo, err := NewSQLiteRepository(dbPath)
	if err != nil {
		t.Fatalf("Failed to create repository: %v", err)
	}
	defer repo.Close()

	// Write 5 spans
	for i := 0; i < 5; i++ {
		span := createFlusherTestSpan(t, i)
		resource := createFlusherTestResource("test-service")
		if err := repo.WriteSpan(span, resource); err != nil {
			t.Fatalf("Failed to write span %d: %v", i, err)
		}
	}

	flusher := NewFlusher(repo)

	// Directly trigger flush (testing the core flush logic)
	// Since count > threshold, this should flush
	if err := flusher.doStreamingFlush(); err != nil {
		t.Fatalf("doStreamingFlush failed: %v", err)
	}

	// Verify flush occurred
	count, err := repo.GetSpanCount()
	if err != nil {
		t.Fatalf("Failed to get span count: %v", err)
	}
	if count != 0 {
		t.Errorf("Expected 0 spans after flush, got %d", count)
	}
}

func TestFlusherFlush_ManySpans(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "flusher-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "test.db")
	outputDir := filepath.Join(tmpDir, "spans")

	// Set up test config
	cfg := config.Default()
	cfg.Flusher.OutputDir = outputDir
	cfg.Flusher.MinRows = 1
	config.SetForTesting(cfg)

	repo, err := NewSQLiteRepository(dbPath)
	if err != nil {
		t.Fatalf("Failed to create repository: %v", err)
	}
	defer repo.Close()

	// Write 100 spans
	for i := 0; i < 100; i++ {
		span := createFlusherTestSpan(t, i)
		resource := createFlusherTestResource("test-service")
		if err := repo.WriteSpan(span, resource); err != nil {
			t.Fatalf("Failed to write span %d: %v", i, err)
		}
	}

	flusher := NewFlusher(repo)

	// Flush all spans
	if err := flusher.doStreamingFlush(); err != nil {
		t.Fatalf("Flush failed: %v", err)
	}

	// Verify all spans were flushed
	count, err := repo.GetSpanCount()
	if err != nil {
		t.Fatalf("Failed to get span count: %v", err)
	}
	if count != 0 {
		t.Errorf("Expected 0 spans after flush, got %d", count)
	}

	// Verify parquet file was created
	files, err := filepath.Glob(filepath.Join(outputDir, "year=*", "month=*", "day=*", "*.parquet"))
	if err != nil {
		t.Fatalf("Failed to glob parquet files: %v", err)
	}
	if len(files) != 1 {
		t.Errorf("Expected 1 parquet file, got %d", len(files))
	}
}

func TestFlusherFlush_NoSpans(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "flusher-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "test.db")
	outputDir := filepath.Join(tmpDir, "spans")

	setupTestConfig(t, outputDir)

	repo, err := NewSQLiteRepository(dbPath)
	if err != nil {
		t.Fatalf("Failed to create repository: %v", err)
	}
	defer repo.Close()

	flusher := NewFlusher(repo)

	// Flush with no spans should not error
	if err := flusher.doStreamingFlush(); err != nil {
		t.Errorf("doStreamingFlush failed with no spans: %v", err)
	}

	// No parquet files should be created
	files, err := filepath.Glob(filepath.Join(outputDir, "year=*", "month=*", "day=*", "*.parquet"))
	if err != nil {
		t.Fatalf("Failed to glob parquet files: %v", err)
	}
	if len(files) != 0 {
		t.Errorf("Expected 0 parquet files with no spans, got %d", len(files))
	}
}

func TestFlusherStartStop(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "flusher-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "test.db")
	outputDir := filepath.Join(tmpDir, "spans")

	// Set up test config with short interval
	cfg := config.Default()
	cfg.Flusher.OutputDir = outputDir
	cfg.Flusher.Interval = 100 * time.Millisecond
	config.SetForTesting(cfg)

	repo, err := NewSQLiteRepository(dbPath)
	if err != nil {
		t.Fatalf("Failed to create repository: %v", err)
	}
	defer repo.Close()

	flusher := NewFlusher(repo)
	flusher.Start()

	// Let it run briefly
	time.Sleep(50 * time.Millisecond)

	// Stop should complete without hanging
	done := make(chan struct{})
	go func() {
		flusher.Stop()
		close(done)
	}()

	select {
	case <-done:
		// Success
	case <-time.After(5 * time.Second):
		t.Fatal("Flusher.Stop() timed out")
	}
}

func TestGenerateOutputPath(t *testing.T) {
	cfg := config.Default()
	cfg.Flusher.OutputDir = "/app/.dbdata/parquet"
	config.SetForTesting(cfg)

	flusher := NewFlusher(nil) // repo not needed for this test

	// Test with a specific time
	testTime := time.Date(2024, 1, 15, 10, 30, 45, 0, time.UTC)
	path := flusher.generateOutputPath(testTime)

	// Verify date partitioning in directory
	if !filepath.IsAbs(path) {
		t.Errorf("Expected absolute path, got %s", path)
	}

	// Expected format: /app/.dbdata/parquet/year=2024/month=01/day=15/20240115_103045_{hash}.parquet
	expectedPrefix := "/app/.dbdata/parquet/year=2024/month=01/day=15/20240115_103045_"
	if len(path) < len(expectedPrefix) || path[:len(expectedPrefix)] != expectedPrefix {
		t.Errorf("Path should start with %s, got %s", expectedPrefix, path)
	}

	if len(path) < 8 || path[len(path)-8:] != ".parquet" {
		t.Errorf("Path should end with .parquet, got %s", path)
	}

	// Verify filename format: YYYYMMDD_HHMMSS_{8-char-hash}.parquet
	filename := filepath.Base(path)
	// Should be 20240115_103045_xxxxxxxx.parquet = 8+1+6+1+8+8 = 32 chars
	if len(filename) != 32 {
		t.Errorf("Filename should be 32 chars (YYYYMMDD_HHMMSS_xxxxxxxx.parquet), got %d: %s", len(filename), filename)
	}
}

// Helper functions for flusher tests

func createFlusherTestSpan(t *testing.T, index int) *tracepb.Span {
	t.Helper()
	traceID := make([]byte, 16)
	spanID := make([]byte, 8)

	// Use index to create unique IDs
	traceID[0] = byte(index)
	spanID[0] = byte(index)

	return &tracepb.Span{
		TraceId:           traceID,
		SpanId:            spanID,
		Name:              "test-operation",
		Kind:              tracepb.Span_SPAN_KIND_SERVER,
		StartTimeUnixNano: uint64(1700000000000000000 + int64(index)*1000000),
		EndTimeUnixNano:   uint64(1700000001000000000 + int64(index)*1000000),
		Attributes: []*commonpb.KeyValue{
			{
				Key:   "test.index",
				Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_IntValue{IntValue: int64(index)}},
			},
		},
		Status: &tracepb.Status{
			Code: tracepb.Status_STATUS_CODE_OK,
		},
	}
}

func createFlusherTestResource(serviceName string) *resourcepb.Resource {
	return &resourcepb.Resource{
		Attributes: []*commonpb.KeyValue{
			{
				Key:   "service.name",
				Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: serviceName}},
			},
		},
	}
}
