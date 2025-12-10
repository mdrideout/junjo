package storage

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"

	"junjo-ai-studio/ingestion/config"
)

// WarmFlusher manages incremental snapshots to warm parquet files.
// These are smaller, more frequent snapshots that sit between cold flushes.
type WarmFlusher struct {
	repo          SpanRepository
	outputDir     string // ./parquet/tmp/
	sizeThreshold int64  // Minimum bytes before triggering snapshot (default 10MB)
	parquetConfig ParquetWriterConfig
}

// NewWarmFlusher creates a new WarmFlusher instance.
func NewWarmFlusher(repo SpanRepository) *WarmFlusher {
	cfg := config.Get().Flusher
	warmDir := filepath.Join(cfg.OutputDir, "tmp")

	return &WarmFlusher{
		repo:          repo,
		outputDir:     warmDir,
		sizeThreshold: cfg.WarmSnapshotBytes,
		parquetConfig: DefaultParquetWriterConfig(),
	}
}

// CheckAndSnapshot checks if a warm snapshot should be created and does so if needed.
// Returns true if a snapshot was created, false otherwise.
func (wf *WarmFlusher) CheckAndSnapshot() (bool, error) {
	// Check size of unflushed data since last warm snapshot
	bytes, err := wf.repo.GetUnflushedBytesSinceWarm()
	if err != nil {
		return false, fmt.Errorf("failed to get unflushed bytes: %w", err)
	}

	// Also get span count for diagnostic purposes
	spanCount, countErr := wf.repo.GetSpanCount()
	if countErr != nil {
		slog.Warn("failed to get span count for warm check", slog.Any("error", countErr))
		spanCount = -1
	}

	slog.Debug("warm snapshot check",
		slog.Int64("unflushed_bytes", bytes),
		slog.Int64("threshold", wf.sizeThreshold),
		slog.Int64("span_count", spanCount),
		slog.String("warm_dir", wf.outputDir),
		slog.Bool("will_snapshot", bytes >= wf.sizeThreshold))

	if bytes < wf.sizeThreshold {
		return false, nil
	}

	slog.Info("warm snapshot threshold exceeded, creating snapshot")

	// Get current warm state to know where to start
	state, err := wf.repo.GetWarmSnapshotState()
	if err != nil {
		return false, fmt.Errorf("failed to get warm snapshot state: %w", err)
	}

	// Get spans since last warm ULID
	records, lastULID, err := wf.repo.GetSpansSinceWarmULID(state.LastWarmULID, SpanFilter{})
	if err != nil {
		return false, fmt.Errorf("failed to get spans for warm snapshot: %w", err)
	}

	if len(records) == 0 {
		slog.Debug("warm snapshot skipped: no new spans")
		return false, nil
	}

	// Ensure output directory exists
	if err := os.MkdirAll(wf.outputDir, 0755); err != nil {
		return false, fmt.Errorf("failed to create warm output directory: %w", err)
	}

	// Generate warm parquet filename
	outputPath := wf.generateWarmPath()

	// Write parquet file
	if err := WriteSpansToParquet(records, outputPath, wf.parquetConfig); err != nil {
		return false, fmt.Errorf("failed to write warm parquet file: %w", err)
	}

	// Update warm snapshot state
	newFileCount := state.WarmFileCount + 1
	if err := wf.repo.UpdateWarmSnapshotState(lastULID, newFileCount); err != nil {
		// Try to clean up the parquet file since we couldn't update state
		os.Remove(outputPath)
		return false, fmt.Errorf("failed to update warm snapshot state: %w", err)
	}

	slog.Info("warm snapshot created",
		slog.Int("span_count", len(records)),
		slog.String("output_path", outputPath),
		slog.Int("warm_file_count", newFileCount),
		slog.Int64("bytes_snapshotted", bytes))

	return true, nil
}

// CleanupWarmFiles deletes all warm parquet files and resets the warm state.
// Called after a cold flush completes.
func (wf *WarmFlusher) CleanupWarmFiles() error {
	// Find all warm files
	pattern := filepath.Join(wf.outputDir, "warm_*.parquet")
	files, err := filepath.Glob(pattern)
	if err != nil {
		return fmt.Errorf("failed to glob warm files: %w", err)
	}

	// Delete each file
	for _, file := range files {
		if err := os.Remove(file); err != nil {
			slog.Warn("failed to delete warm file",
				slog.String("file", file),
				slog.Any("error", err))
			// Continue deleting other files
		}
	}

	// Reset warm snapshot state
	if err := wf.repo.ResetWarmSnapshotState(); err != nil {
		return fmt.Errorf("failed to reset warm snapshot state: %w", err)
	}

	if len(files) > 0 {
		slog.Info("warm files cleaned up", slog.Int("file_count", len(files)))
	}

	return nil
}

// GetWarmFilePaths returns the paths of all warm parquet files.
// Used by Python to include warm files in DataFusion queries.
func (wf *WarmFlusher) GetWarmFilePaths() ([]string, error) {
	pattern := filepath.Join(wf.outputDir, "warm_*.parquet")
	return filepath.Glob(pattern)
}

// generateWarmPath creates the output path for a warm parquet file.
// Format: {output_dir}/tmp/warm_{ulid}.parquet
func (wf *WarmFlusher) generateWarmPath() string {
	// Generate random suffix for uniqueness
	hashBytes := make([]byte, 8)
	rand.Read(hashBytes)
	hashSuffix := hex.EncodeToString(hashBytes)

	filename := fmt.Sprintf("warm_%s.parquet", hashSuffix)
	return filepath.Join(wf.outputDir, filename)
}
