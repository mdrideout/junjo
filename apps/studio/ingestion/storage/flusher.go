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

	"crawshaw.io/sqlite/sqlitex"
)

// FlusherConfig holds configuration for the Flusher.
type FlusherConfig struct {
	// FlushInterval is how often to check for flush conditions.
	FlushInterval time.Duration

	// MaxFlushAge triggers flush when oldest unflushed span exceeds this age.
	MaxFlushAge time.Duration

	// MaxRowCount triggers flush when row count exceeds this threshold.
	MaxRowCount int64

	// MinRowCount prevents flushing tiny batches.
	MinRowCount int64

	// OutputDir is the base directory for Parquet files (SPAN_STORAGE_PATH).
	OutputDir string

	// ParquetConfig is the configuration for Parquet writing.
	ParquetConfig ParquetWriterConfig
}

// DefaultFlusherConfig returns the default flusher configuration.
func DefaultFlusherConfig() FlusherConfig {
	return FlusherConfig{
		FlushInterval: 30 * time.Second,
		MaxFlushAge:   1 * time.Hour,
		MaxRowCount:   100000,
		MinRowCount:   1000,
		OutputDir:     "/app/.dbdata/spans",
		ParquetConfig: DefaultParquetWriterConfig(),
	}
}

// Flusher manages the background process of flushing spans from SQLite to Parquet.
type Flusher struct {
	storage *Storage
	config  FlusherConfig

	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup

	// For manual flush requests
	flushCh chan chan error
}

// NewFlusher creates a new Flusher instance.
func NewFlusher(storage *Storage, config FlusherConfig) *Flusher {
	ctx, cancel := context.WithCancel(context.Background())
	return &Flusher{
		storage: storage,
		config:  config,
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
		slog.Duration("interval", f.config.FlushInterval),
		slog.Duration("max_age", f.config.MaxFlushAge),
		slog.Int64("max_rows", f.config.MaxRowCount),
		slog.String("output_dir", f.config.OutputDir))
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

	ticker := time.NewTicker(f.config.FlushInterval)
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
	count, err := f.storage.GetSpanCount()
	if err != nil {
		return fmt.Errorf("failed to get span count: %w", err)
	}

	if count == 0 {
		slog.Debug("no spans to flush")
		return nil
	}

	// Check row count threshold
	if count >= f.config.MaxRowCount {
		slog.Info("flush triggered by row count",
			slog.Int64("count", count),
			slog.Int64("threshold", f.config.MaxRowCount))
		return f.doFlush()
	}

	// Check age threshold
	flushState, err := f.storage.GetFlushState()
	if err != nil {
		return fmt.Errorf("failed to get flush state: %w", err)
	}

	// If we've never flushed, check if we have enough rows
	if flushState.LastFlushTime.IsZero() {
		if count >= f.config.MinRowCount {
			slog.Info("flush triggered: first flush with sufficient rows",
				slog.Int64("count", count))
			return f.doFlush()
		}
		return nil
	}

	// Check if max age exceeded
	age := time.Since(flushState.LastFlushTime)
	if age >= f.config.MaxFlushAge && count >= f.config.MinRowCount {
		slog.Info("flush triggered by age",
			slog.Duration("age", age),
			slog.Duration("threshold", f.config.MaxFlushAge),
			slog.Int64("count", count))
		return f.doFlush()
	}

	return nil
}

// doFlush performs the actual flush operation.
func (f *Flusher) doFlush() error {
	startTime := time.Now()

	// Get a connection for the transaction
	conn := f.storage.pool.Get(nil)
	if conn == nil {
		return fmt.Errorf("failed to get connection from pool")
	}
	defer f.storage.pool.Put(conn)

	var err error
	defer sqlitex.Save(conn)(&err)

	// Read all spans
	records, firstKey, lastKey, err := f.readAllSpansForFlush()
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
	if err := WriteSpansToParquet(records, outputPath, f.config.ParquetConfig); err != nil {
		return fmt.Errorf("failed to write parquet file: %w", err)
	}

	// Delete flushed spans from SQLite
	if err := f.deleteSpansInRange(firstKey, lastKey); err != nil {
		// Try to remove the Parquet file since we couldn't complete the transaction
		os.Remove(outputPath)
		return fmt.Errorf("failed to delete flushed spans: %w", err)
	}

	// Update flush state
	if err := f.storage.UpdateFlushState(firstKey, lastKey, int64(len(records))); err != nil {
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

// readAllSpansForFlush reads all spans from SQLite and converts them to SpanRecords.
// Returns the records, first key, last key, and any error.
func (f *Flusher) readAllSpansForFlush() ([]SpanRecord, []byte, []byte, error) {
	var records []SpanRecord
	var firstKey, lastKey []byte

	conn := f.storage.pool.Get(nil)
	if conn == nil {
		return nil, nil, nil, fmt.Errorf("failed to get connection from pool")
	}
	defer f.storage.pool.Put(conn)

	stmt := conn.Prep("SELECT key_ulid, span_bytes FROM spans ORDER BY key_ulid")
	defer stmt.Reset()

	for {
		hasRow, err := stmt.Step()
		if err != nil {
			return nil, nil, nil, fmt.Errorf("failed to step: %w", err)
		}
		if !hasRow {
			break
		}

		// Read key
		keyLen := stmt.ColumnLen(0)
		key := make([]byte, keyLen)
		stmt.ColumnBytes(0, key)

		if firstKey == nil {
			firstKey = key
		}
		lastKey = key

		// Read span data
		dataLen := stmt.ColumnLen(1)
		dataBytes := make([]byte, dataLen)
		stmt.ColumnBytes(1, dataBytes)

		// Unmarshal span data
		spanData, err := UnmarshalSpanData(dataBytes)
		if err != nil {
			slog.Warn("error unmarshaling span data during flush, skipping",
				slog.String("key", fmt.Sprintf("%x", key)),
				slog.Any("error", err))
			continue
		}

		// Convert to record
		record := ConvertSpanDataToRecord(spanData)
		records = append(records, record)
	}

	return records, firstKey, lastKey, nil
}

// deleteSpansInRange deletes all spans with keys between firstKey and lastKey (inclusive).
func (f *Flusher) deleteSpansInRange(firstKey, lastKey []byte) error {
	conn := f.storage.pool.Get(nil)
	if conn == nil {
		return fmt.Errorf("failed to get connection from pool")
	}
	defer f.storage.pool.Put(conn)

	stmt := conn.Prep("DELETE FROM spans WHERE key_ulid >= ? AND key_ulid <= ?")
	defer stmt.Reset()

	stmt.BindBytes(1, firstKey)
	stmt.BindBytes(2, lastKey)

	_, err := stmt.Step()
	if err != nil {
		return fmt.Errorf("failed to delete spans: %w", err)
	}

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
		f.config.OutputDir,
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
