package storage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"time"

	"junjo-ai-studio/ingestion/config"
)

// flusherConfig holds internal configuration for the Flusher.
type flusherConfig struct {
	flushInterval time.Duration
	maxFlushAge   time.Duration
	maxRowCount   int64
	minRowCount   int64
	outputDir     string
	parquetConfig ParquetWriterConfig
}

// Flusher manages the background process of flushing spans from SQLite to Parquet.
type Flusher struct {
	repo   SpanRepository
	config flusherConfig

	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup

	// For manual flush requests
	flushCh chan chan error
}

// NewFlusher creates a new Flusher instance.
func NewFlusher(repo SpanRepository) *Flusher {
	cfg := config.Get().Flusher
	ctx, cancel := context.WithCancel(context.Background())
	return &Flusher{
		repo: repo,
		config: flusherConfig{
			flushInterval: cfg.Interval,
			maxFlushAge:   cfg.MaxAge,
			maxRowCount:   cfg.MaxRows,
			minRowCount:   cfg.MinRows,
			outputDir:     cfg.OutputDir,
			parquetConfig: DefaultParquetWriterConfig(),
		},
		ctx:     ctx,
		cancel:  cancel,
		flushCh: make(chan chan error),
	}
}

// Start begins the background flusher process.
func (f *Flusher) Start() {
	f.wg.Add(1)
	go f.run()
	slog.Info("flusher started",
		slog.Duration("interval", f.config.flushInterval),
		slog.Duration("max_age", f.config.maxFlushAge),
		slog.Int64("max_rows", f.config.maxRowCount),
		slog.String("output_dir", f.config.outputDir))
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
func (f *Flusher) run() {
	defer f.wg.Done()

	ticker := time.NewTicker(f.config.flushInterval)
	defer ticker.Stop()

	for {
		select {
		case <-f.ctx.Done():
			// Perform final flush before stopping
			slog.Info("performing final flush before shutdown")
			if err := f.doFlush(); err != nil {
				slog.Error("final flush failed", slog.Any("error", err))
			}
			return

		case <-ticker.C:
			if err := f.checkAndFlush(); err != nil {
				slog.Error("periodic flush check failed", slog.Any("error", err))
			}

		case resultCh := <-f.flushCh:
			// Manual flush request
			err := f.doFlush()
			resultCh <- err
		}
	}
}

// checkAndFlush checks if flush conditions are met and flushes if so.
func (f *Flusher) checkAndFlush() error {
	// Get current span count
	count, err := f.repo.GetSpanCount()
	if err != nil {
		return fmt.Errorf("failed to get span count: %w", err)
	}

	if count == 0 {
		slog.Debug("no spans to flush")
		return nil
	}

	// Check row count threshold
	if count >= f.config.maxRowCount {
		slog.Info("flush triggered by row count",
			slog.Int64("count", count),
			slog.Int64("threshold", f.config.maxRowCount))
		return f.doFlush()
	}

	// Check age threshold
	flushState, err := f.repo.GetFlushState()
	if err != nil {
		return fmt.Errorf("failed to get flush state: %w", err)
	}

	// If we've never flushed, check if we have enough rows
	if flushState.LastFlushTime.IsZero() {
		if count >= f.config.minRowCount {
			slog.Info("flush triggered: first flush with sufficient rows",
				slog.Int64("count", count))
			return f.doFlush()
		}
		return nil
	}

	// Check if max age exceeded
	age := time.Since(flushState.LastFlushTime)
	if age >= f.config.maxFlushAge && count >= f.config.minRowCount {
		slog.Info("flush triggered by age",
			slog.Duration("age", age),
			slog.Duration("threshold", f.config.maxFlushAge),
			slog.Int64("count", count))
		return f.doFlush()
	}

	return nil
}

// doFlush performs the actual flush operation.
func (f *Flusher) doFlush() error {
	startTime := time.Now()

	// Read all spans
	records, firstKey, lastKey, err := f.repo.ReadAllSpansForFlush()
	if err != nil {
		return fmt.Errorf("failed to read spans: %w", err)
	}

	if len(records) == 0 {
		slog.Debug("no spans to flush after read")
		return nil
	}

	// Determine output path with date partitioning
	now := time.Now().UTC()
	outputPath := f.generateOutputPath(now, records[0].ServiceName)

	// Write Parquet file
	if err := WriteSpansToParquet(records, outputPath, f.config.parquetConfig); err != nil {
		return fmt.Errorf("failed to write parquet file: %w", err)
	}

	// Delete flushed spans from SQLite
	if err := f.repo.DeleteSpansInRange(firstKey, lastKey); err != nil {
		// Try to remove the Parquet file since we couldn't complete the transaction
		os.Remove(outputPath)
		return fmt.Errorf("failed to delete flushed spans: %w", err)
	}

	// Update flush state
	if err := f.repo.UpdateFlushState(firstKey, lastKey, int64(len(records))); err != nil {
		slog.Warn("failed to update flush state", slog.Any("error", err))
		// Don't fail the flush for this
	}

	duration := time.Since(startTime)
	slog.Info("flush completed",
		slog.Int("span_count", len(records)),
		slog.String("output_path", outputPath),
		slog.Duration("duration", duration))

	return nil
}

// generateOutputPath creates the output path for a Parquet file.
// Format: {output_dir}/year=YYYY/month=MM/day=DD/{service}_{timestamp}_{uuid8}.parquet
func (f *Flusher) generateOutputPath(t time.Time, serviceName string) string {
	// Sanitize service name for filesystem
	safeServiceName := sanitizeServiceName(serviceName)

	// Generate random UUID suffix (8 chars)
	uuidBytes := make([]byte, 4)
	rand.Read(uuidBytes)
	uuidSuffix := hex.EncodeToString(uuidBytes)

	// Build path with date partitioning
	dateDir := filepath.Join(
		f.config.outputDir,
		fmt.Sprintf("year=%04d", t.Year()),
		fmt.Sprintf("month=%02d", t.Month()),
		fmt.Sprintf("day=%02d", t.Day()),
	)

	filename := fmt.Sprintf("%s_%d_%s.parquet",
		safeServiceName,
		t.Unix(),
		uuidSuffix,
	)

	return filepath.Join(dateDir, filename)
}

// sanitizeServiceName makes a service name safe for use in filesystem paths.
func sanitizeServiceName(name string) string {
	if name == "" {
		return "unknown"
	}

	// Replace problematic characters with underscores
	result := make([]byte, 0, len(name))
	for i := 0; i < len(name); i++ {
		c := name[i]
		if (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
			(c >= '0' && c <= '9') || c == '-' || c == '_' {
			result = append(result, c)
		} else {
			result = append(result, '_')
		}
	}

	// Limit length
	if len(result) > 64 {
		result = result[:64]
	}

	return string(result)
}
