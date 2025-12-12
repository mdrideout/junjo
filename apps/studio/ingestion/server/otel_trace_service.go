package server

import (
	"context"
	"encoding/hex"
	"fmt"
	"log/slog"
	"runtime"
	"sync/atomic"
	"time"

	"junjo-ai-studio/ingestion/config"
	"junjo-ai-studio/ingestion/storage"

	coltracepb "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type OtelTraceService struct {
	coltracepb.UnimplementedTraceServiceServer
	repo       storage.SpanRepository
	spanLogger *BatchedSpanLogger

	// Backpressure configuration (from config)
	backpressureMaxBytes    int64
	backpressureCheckInterval time.Duration

	// Backpressure state (cached to avoid checking on every request)
	underPressure     atomic.Bool
	lastPressureCheck atomic.Int64 // Unix nano timestamp
}

// NewOtelTraceService creates a new trace service.
func NewOtelTraceService(repo storage.SpanRepository, spanLogger *BatchedSpanLogger) *OtelTraceService {
	cfg := config.Get().Server
	svc := &OtelTraceService{
		repo:                      repo,
		spanLogger:                spanLogger,
		backpressureMaxBytes:      cfg.BackpressureMaxBytes,
		backpressureCheckInterval: time.Duration(cfg.BackpressureCheckInterval) * time.Second,
	}
	slog.Info("trace service initialized",
		slog.String("backpressure_max", formatMB(svc.backpressureMaxBytes)),
		slog.Duration("backpressure_check_interval", svc.backpressureCheckInterval))
	return svc
}

// checkBackpressure checks if we should apply backpressure (cached check).
// Uses Go heap allocation (Alloc) to measure actual memory pressure.
func (s *OtelTraceService) checkBackpressure() bool {
	now := time.Now().UnixNano()
	lastCheck := s.lastPressureCheck.Load()

	// Only check periodically to avoid overhead on every request
	if now-lastCheck < int64(s.backpressureCheckInterval) {
		return s.underPressure.Load()
	}

	// Update check timestamp
	if !s.lastPressureCheck.CompareAndSwap(lastCheck, now) {
		// Another goroutine is checking, use cached value
		return s.underPressure.Load()
	}

	// Check Go heap allocation - this is actual memory in use
	var memStats runtime.MemStats
	runtime.ReadMemStats(&memStats)
	heapAlloc := int64(memStats.Alloc)

	isUnderPressure := heapAlloc >= s.backpressureMaxBytes
	wasUnderPressure := s.underPressure.Swap(isUnderPressure)

	// Log state changes
	if isUnderPressure && !wasUnderPressure {
		slog.Warn("backpressure activated",
			slog.String("heap_alloc", formatMB(heapAlloc)),
			slog.String("threshold", formatMB(s.backpressureMaxBytes)))
	} else if !isUnderPressure && wasUnderPressure {
		slog.Info("backpressure released",
			slog.String("heap_alloc", formatMB(heapAlloc)),
			slog.String("threshold", formatMB(s.backpressureMaxBytes)))
	}

	return isUnderPressure
}

// formatMB formats bytes as MB string for logging.
func formatMB(bytes int64) string {
	return fmt.Sprintf("%.1fMB", float64(bytes)/(1024*1024))
}

func (s *OtelTraceService) Export(ctx context.Context, req *coltracepb.ExportTraceServiceRequest) (*coltracepb.ExportTraceServiceResponse, error) {
	// Check backpressure - reject if system is overloaded
	if s.checkBackpressure() {
		return nil, status.Error(codes.ResourceExhausted,
			"ingestion service is under pressure, please retry later")
	}

	// Collect all spans into a batch for efficient writing
	var batch []*storage.SpanWriteRequest

	for _, resourceSpans := range req.ResourceSpans {
		resource := resourceSpans.Resource
		for _, scopeSpans := range resourceSpans.ScopeSpans {
			for _, span := range scopeSpans.Spans {
				traceID := hex.EncodeToString(span.TraceId)
				spanID := hex.EncodeToString(span.SpanId)

				// Log to batched logger (flushed periodically)
				s.spanLogger.LogSpan(traceID, spanID)

				// Add to batch
				batch = append(batch, &storage.SpanWriteRequest{
					Span:     span,
					Resource: resource,
				})
			}
		}
	}

	// Write all spans in a single transaction (much more efficient)
	if len(batch) > 0 {
		if err := s.repo.WriteSpans(batch); err != nil {
			slog.ErrorContext(ctx, "error writing spans batch to wal",
				slog.Int("count", len(batch)),
				slog.Any("error", err))
			// For a WAL, we generally want to be resilient, so we'll log and continue.
		}
	}

	// Return a success response to the client
	return &coltracepb.ExportTraceServiceResponse{}, nil
}
