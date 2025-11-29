package server

import (
	"context"
	"encoding/hex"
	"log/slog"

	"junjo-ai-studio/ingestion/storage"

	coltracepb "go.opentelemetry.io/proto/otlp/collector/trace/v1"
)

type OtelTraceService struct {
	coltracepb.UnimplementedTraceServiceServer
	repo storage.SpanRepository
}

// NewOtelTraceService creates a new trace service.
func NewOtelTraceService(repo storage.SpanRepository) *OtelTraceService {
	return &OtelTraceService{repo: repo}
}

func (s *OtelTraceService) Export(ctx context.Context, req *coltracepb.ExportTraceServiceRequest) (*coltracepb.ExportTraceServiceResponse, error) {
	for _, resourceSpans := range req.ResourceSpans {
		resource := resourceSpans.Resource
		for _, scopeSpans := range resourceSpans.ScopeSpans {
			for _, span := range scopeSpans.Spans {
				traceID := hex.EncodeToString(span.TraceId)
				spanID := hex.EncodeToString(span.SpanId)
				slog.InfoContext(ctx, "received span", slog.String("span_id", spanID), slog.String("trace_id", traceID), slog.String("name", span.Name))

				// Write the span to the WAL
				if err := s.repo.WriteSpan(span, resource); err != nil {
					slog.ErrorContext(ctx, "error writing span to wal", slog.Any("error", err))
					// Decide on error handling: continue, or return an error to the client?
					// For a WAL, we generally want to be resilient, so we'll log and continue.
				}
			}
		}
	}

	// Return a success response to the client
	return &coltracepb.ExportTraceServiceResponse{}, nil
}
