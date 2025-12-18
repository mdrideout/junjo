package storage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log/slog"
	"path/filepath"
	"runtime"
	"sync"
	"sync/atomic"
	"time"

	"junjo-ai-studio/ingestion/config"
)

// DefaultFlushChunks is the default number of chunks to split a flush into
const DefaultFlushChunks = 10

// EstimatedAvgSpanBytes is the estimated average size of a span in bytes
// Used to calculate spans per chunk from byte-based chunk size
const EstimatedAvgSpanBytes = 500

// flusherConfig holds internal configuration for the Flusher.
type flusherConfig struct {
	flushInterval time.Duration
	maxFlushAge   time.Duration
	maxRowCount   int64
	minRowCount   int64
	maxBytes      int64
	outputDir     string
	parquetConfig ParquetWriterConfig
	chunkSize     int // Chunk size in spans for streaming flush
}

// FlushNotifyFunc is called after a cold flush with the path to the new parquet file.
// Used to notify the backend for immediate indexing.
type FlushNotifyFunc func(ctx context.Context, filePath string) error

// Flusher manages the background process of flushing spans from SQLite to Parquet.
// Uses a simple two-tier architecture: Hot (SQLite) -> Cold (Parquet).
// Reactive flush triggering via signal channel when byte threshold exceeded.
type Flusher struct {
	repo   SpanRepository
	config flusherConfig

	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup

	// Reactive cold flush signal (triggered by byte threshold in repository)
	coldSignalCh chan struct{}

	// For manual flush requests
	flushCh chan chan error

	// Cold flush state (for non-blocking)
	coldFlushRunning atomic.Bool
	coldFlushMu      sync.Mutex

	// Optional callback to notify backend after flush
	notifyFunc FlushNotifyFunc
}

// NewFlusher creates a new Flusher instance.
func NewFlusher(repo SpanRepository) *Flusher {
	cfg := config.Get().Flusher
	ctx, cancel := context.WithCancel(context.Background())

	// Create cold signal channel (buffered to avoid blocking writers)
	coldSignalCh := make(chan struct{}, 1)

	// Register signal channel with repository for reactive triggering
	// (skip if repo is nil - for testing)
	if repo != nil {
		repo.SetColdSignalChannel(coldSignalCh)
	}

	// Calculate chunk size from FlushChunks and MaxBytes
	// Chunk size in spans = (MaxBytes / FlushChunks) / EstimatedAvgSpanBytes
	flushChunks := cfg.FlushChunks
	if flushChunks <= 0 {
		flushChunks = DefaultFlushChunks
	}
	chunkBytes := cfg.MaxBytes / int64(flushChunks)
	chunkSize := int(chunkBytes / EstimatedAvgSpanBytes)
	if chunkSize < 100 {
		chunkSize = 100 // Minimum 100 spans per chunk
	}

	f := &Flusher{
		repo: repo,
		config: flusherConfig{
			flushInterval: cfg.Interval,
			maxFlushAge:   cfg.MaxAge,
			maxRowCount:   cfg.MaxRows,
			minRowCount:   cfg.MinRows,
			maxBytes:      cfg.MaxBytes,
			outputDir:     cfg.OutputDir,
			parquetConfig: DefaultParquetWriterConfig(),
			chunkSize:     chunkSize,
		},
		ctx:          ctx,
		cancel:       cancel,
		coldSignalCh: coldSignalCh,
		flushCh:      make(chan chan error),
	}

	return f
}

// Start begins the background flusher process.
func (f *Flusher) Start() {
	f.wg.Add(1)
	go f.run()
	slog.Info("flusher started (two-tier: hot->cold, reactive triggering)",
		slog.Duration("max_age", f.config.maxFlushAge),
		slog.Int64("max_rows", f.config.maxRowCount),
		slog.Int64("max_bytes", f.config.maxBytes),
		slog.Int("chunk_size_spans", f.config.chunkSize),
		slog.String("output_dir", f.config.outputDir))
}

// SetNotifyFunc sets the callback to notify the backend after a cold flush.
// Must be called before Start().
func (f *Flusher) SetNotifyFunc(fn FlushNotifyFunc) {
	f.notifyFunc = fn
}

// Stop gracefully stops the flusher and waits for completion.
func (f *Flusher) Stop() {
	slog.Info("stopping flusher")
	f.cancel()
	f.wg.Wait()
	slog.Info("flusher stopped")
}

// Flush triggers an immediate flush and waits for completion.
// Returns error if flush fails.
func (f *Flusher) Flush() error {
	resultCh := make(chan error, 1)
	select {
	case f.flushCh <- resultCh:
		return <-resultCh
	case <-f.ctx.Done():
		return f.ctx.Err()
	}
}

// run is the main loop for the flusher.
// Uses reactive cold flush signals - triggers immediately when byte threshold exceeded.
func (f *Flusher) run() {
	defer f.wg.Done()

	// Fallback ticker for age-based flush checks (less frequent - mainly for max_age trigger)
	fallbackTicker := time.NewTicker(60 * time.Second)
	defer fallbackTicker.Stop()

	for {
		select {
		case <-f.ctx.Done():
			// Perform final flush before stopping (blocking, must complete)
			slog.Info("performing final flush before shutdown")
			if err := f.doStreamingFlush(); err != nil {
				slog.Error("final flush failed", slog.Any("error", err))
			}
			return

		case <-f.coldSignalCh:
			// Reactive cold flush triggered by byte threshold
			// Skip if flush already running (threshold will re-trigger after flush completes if needed)
			if f.coldFlushRunning.Load() {
				slog.Debug("cold signal received but flush already running, ignoring")
				continue
			}
			slog.Info("cold signal received, triggering cold flush")
			f.triggerColdFlushAsync()

		case <-fallbackTicker.C:
			// Fallback check for age-based triggers (row count, max age)
			// Skip if flush already running
			if f.coldFlushRunning.Load() {
				slog.Debug("fallback check skipped, flush already running")
				continue
			}
			f.checkAndFlushAsync()

		case resultCh := <-f.flushCh:
			// Manual flush request (blocking - caller waits)
			err := f.doStreamingFlush()
			resultCh <- err
		}
	}
}

// checkAndFlushAsync checks if cold flush conditions are met and triggers non-blocking flush.
func (f *Flusher) checkAndFlushAsync() {
	// Skip if cold flush already running
	if f.coldFlushRunning.Load() {
		slog.Debug("cold flush already running, skipping check")
		return
	}

	// Get current span count
	count, err := f.repo.GetSpanCount()
	if err != nil {
		slog.Error("failed to get span count for cold check", slog.Any("error", err))
		return
	}

	if count == 0 {
		slog.Debug("no spans for cold flush")
		return
	}

	// Check row count threshold
	if count >= f.config.maxRowCount {
		slog.Info("cold flush triggered by row count",
			slog.Int64("count", count),
			slog.Int64("threshold", f.config.maxRowCount))
		f.triggerColdFlushAsync()
		return
	}

	// Check size threshold (use actual span data size, not DB file size)
	if f.config.maxBytes > 0 {
		dataSize, err := f.repo.GetSpanDataSize()
		if err != nil {
			slog.Warn("failed to get span data size for cold check", slog.Any("error", err))
		} else if dataSize >= f.config.maxBytes {
			slog.Info("cold flush triggered by size",
				slog.Int64("data_size_bytes", dataSize),
				slog.Int64("threshold_bytes", f.config.maxBytes))
			f.triggerColdFlushAsync()
			return
		}
	}

	// Check age threshold (fallback)
	flushState, err := f.repo.GetFlushState()
	if err != nil {
		slog.Error("failed to get flush state for cold check", slog.Any("error", err))
		return
	}

	// If we've never flushed, check if we have enough rows
	if flushState.LastFlushTime.IsZero() {
		if count >= f.config.minRowCount {
			slog.Info("cold flush triggered: first flush with sufficient rows",
				slog.Int64("count", count))
			f.triggerColdFlushAsync()
		}
		return
	}

	// Check if max age exceeded
	age := time.Since(flushState.LastFlushTime)
	if age >= f.config.maxFlushAge && count >= f.config.minRowCount {
		slog.Info("cold flush triggered by age",
			slog.Duration("age", age),
			slog.Duration("threshold", f.config.maxFlushAge),
			slog.Int64("count", count))
		f.triggerColdFlushAsync()
	}
}

// triggerColdFlushAsync starts a cold flush in the background.
func (f *Flusher) triggerColdFlushAsync() {
	// Use CAS to ensure only one flush runs at a time
	if !f.coldFlushRunning.CompareAndSwap(false, true) {
		slog.Debug("cold flush already running, skipping trigger")
		return
	}

	// Run flush in background goroutine
	go func() {
		defer f.coldFlushRunning.Store(false)

		slog.Info("starting background cold flush (streaming)")
		if err := f.doStreamingFlush(); err != nil {
			slog.Error("background cold flush failed", slog.Any("error", err))
		}
	}()
}

// doStreamingFlush performs streaming cold flush with bounded memory.
// Reads/writes/deletes in chunks to avoid memory spikes.
func (f *Flusher) doStreamingFlush() error {
	f.coldFlushMu.Lock()
	defer f.coldFlushMu.Unlock()

	startTime := time.Now()

	// Determine output path with date partitioning
	now := time.Now().UTC()
	outputPath := f.generateOutputPath(now)

	// Create streaming parquet writer
	writer, err := NewStreamingParquetWriter(outputPath, f.config.parquetConfig)
	if err != nil {
		return fmt.Errorf("failed to create streaming writer: %w", err)
	}

	var firstKey, lastKey []byte
	var totalRecords int
	var cursor []byte // Start from beginning

	// Process chunks until no more data
	for {
		// Read a chunk of spans (returns pooled slice)
		recordsPtr, chunkFirstKey, chunkLastKey, hasMore, err := f.repo.ReadSpansChunked(cursor, f.config.chunkSize)
		if err != nil {
			writer.Abort()
			return fmt.Errorf("failed to read chunk: %w", err)
		}

		if recordsPtr == nil || len(*recordsPtr) == 0 {
			if recordsPtr != nil {
				ReleaseSpanRecords(recordsPtr) // Return empty slice to pool
			}
			break // No more data
		}

		records := *recordsPtr
		chunkLen := len(records)

		// Track overall first/last keys
		if firstKey == nil {
			firstKey = chunkFirstKey
		}
		lastKey = chunkLastKey

		// Write chunk to parquet (creates new row group)
		if err := writer.WriteChunk(records); err != nil {
			ReleaseSpanRecords(recordsPtr) // Return to pool on error
			writer.Abort()
			return fmt.Errorf("failed to write chunk: %w", err)
		}

		totalRecords += chunkLen

		// Delete this chunk from SQLite immediately (bounded WAL growth)
		if err := f.repo.DeleteSpansInRange(chunkFirstKey, chunkLastKey); err != nil {
			ReleaseSpanRecords(recordsPtr) // Return to pool on error
			writer.Abort()
			return fmt.Errorf("failed to delete chunk: %w", err)
		}

		// Return slice to pool - we're done with this chunk
		ReleaseSpanRecords(recordsPtr)

		slog.Debug("flushed chunk",
			slog.Int("chunk_records", chunkLen),
			slog.Int("total_records", totalRecords),
			slog.Bool("has_more", hasMore))

		if !hasMore {
			break
		}

		// Move cursor past this chunk for next iteration
		cursor = chunkLastKey
	}

	// No data to flush
	if totalRecords == 0 {
		writer.Abort()
		slog.Debug("no spans to flush after streaming read")
		return nil
	}

	// Finalize parquet file
	finalPath, err := writer.Close()
	if err != nil {
		return fmt.Errorf("failed to finalize parquet file: %w", err)
	}

	// Update flush state
	if err := f.repo.UpdateFlushState(firstKey, lastKey, int64(totalRecords)); err != nil {
		slog.Warn("failed to update flush state", slog.Any("error", err))
		// Don't fail the flush for this
	}

	// Reset byte counter since all data is now cold
	f.repo.ResetBytesSinceCold()

	// Release memory after flush:
	// 1. Clear string interning pool (prevents unbounded growth)
	// 2. Force GC to reclaim Arrow allocator caches and other buffers
	// Note: GOMEMLIMIT only helps when *approaching* the limit, not after flush
	// when heap has already dropped. Without explicit GC, memory stays allocated.
	ClearInternPool()
	runtime.GC()

	// Notify backend to index the new file immediately (if callback set)
	if f.notifyFunc != nil {
		if err := f.notifyFunc(f.ctx, finalPath); err != nil {
			slog.Warn("failed to notify backend of new parquet file",
				slog.String("file_path", finalPath),
				slog.Any("error", err))
			// Don't fail the flush - backend will pick it up via polling
		}
	}

	totalRecordsWritten, rowGroups := writer.Stats()
	duration := time.Since(startTime)
	slog.Info("streaming cold flush completed",
		slog.Int("span_count", totalRecordsWritten),
		slog.Int("row_groups", rowGroups),
		slog.Int("chunk_size", f.config.chunkSize),
		slog.String("output_path", finalPath),
		slog.Duration("duration", duration))

	return nil
}

// generateOutputPath creates the output path for a Parquet file.
// Format: {output_dir}/year=YYYY/month=MM/day=DD/YYYYMMDD_HHMMSS_{hash}.parquet
func (f *Flusher) generateOutputPath(t time.Time) string {
	// Generate random hash suffix (8 chars)
	hashBytes := make([]byte, 4)
	rand.Read(hashBytes)
	hashSuffix := hex.EncodeToString(hashBytes)

	// Build path with date partitioning
	dateDir := filepath.Join(
		f.config.outputDir,
		fmt.Sprintf("year=%04d", t.Year()),
		fmt.Sprintf("month=%02d", t.Month()),
		fmt.Sprintf("day=%02d", t.Day()),
	)

	// Filename: YYYYMMDD_HHMMSS_{hash}.parquet
	filename := fmt.Sprintf("%04d%02d%02d_%02d%02d%02d_%s.parquet",
		t.Year(), t.Month(), t.Day(),
		t.Hour(), t.Minute(), t.Second(),
		hashSuffix,
	)

	return filepath.Join(dateDir, filename)
}
