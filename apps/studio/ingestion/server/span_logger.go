package server

import (
	"context"
	"log/slog"
	"sync"
	"time"
)

// SpanLogEntry represents a received span for batched logging.
type SpanLogEntry struct {
	TraceID string
	SpanID  string
}

// BatchedSpanLogger accumulates span receipts and logs them periodically.
type BatchedSpanLogger struct {
	mu       sync.Mutex
	entries  []SpanLogEntry
	interval time.Duration
	stopCh   chan struct{}
	doneCh   chan struct{}
}

// NewBatchedSpanLogger creates a logger that batches span logs.
// interval is how often to flush the batch to logs (e.g., 10*time.Second).
func NewBatchedSpanLogger(interval time.Duration) *BatchedSpanLogger {
	return &BatchedSpanLogger{
		entries:  make([]SpanLogEntry, 0, 100),
		interval: interval,
		stopCh:   make(chan struct{}),
		doneCh:   make(chan struct{}),
	}
}

// Start begins the background goroutine that flushes logs periodically.
func (b *BatchedSpanLogger) Start() {
	go b.run()
}

// Stop signals the logger to stop and waits for it to finish.
func (b *BatchedSpanLogger) Stop() {
	close(b.stopCh)
	<-b.doneCh
}

// LogSpan records a span to be logged in the next batch.
func (b *BatchedSpanLogger) LogSpan(traceID, spanID string) {
	b.mu.Lock()
	b.entries = append(b.entries, SpanLogEntry{
		TraceID: traceID,
		SpanID:  spanID,
	})
	b.mu.Unlock()
}

func (b *BatchedSpanLogger) run() {
	defer close(b.doneCh)

	ticker := time.NewTicker(b.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			b.flush()
		case <-b.stopCh:
			b.flush() // Final flush before stopping
			return
		}
	}
}

func (b *BatchedSpanLogger) flush() {
	b.mu.Lock()
	entries := b.entries
	b.entries = make([]SpanLogEntry, 0, 100)
	b.mu.Unlock()

	if len(entries) == 0 {
		return
	}

	// Count unique traces
	seen := make(map[string]bool)
	for _, e := range entries {
		seen[e.TraceID] = true
	}

	// Log summary at INFO level
	slog.Info("received spans",
		slog.Int("count", len(entries)),
		slog.Int("traces", len(seen)),
	)

	// Log span + trace ID pairs at DEBUG level
	if slog.Default().Enabled(context.Background(), slog.LevelDebug) {
		for _, e := range entries {
			slog.Debug("span received",
				slog.String("trace_id", e.TraceID),
				slog.String("span_id", e.SpanID),
			)
		}
	}
}
