package server

import (
	"context"
	"log/slog"

	colmetricpb "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
)

type OtelMetricService struct {
	colmetricpb.UnimplementedMetricsServiceServer
}

// NewOtelMetricService creates a new metrics service.
func NewOtelMetricService() *OtelMetricService {
	return &OtelMetricService{}
}

func (s *OtelMetricService) Export(ctx context.Context, req *colmetricpb.ExportMetricsServiceRequest) (*colmetricpb.ExportMetricsServiceResponse, error) {
	// For now, we just log that we received metrics.
	// In the future, these could also be written to the WAL.
	slog.InfoContext(ctx, "received resource metrics", slog.Int("count", len(req.ResourceMetrics)))
	return &colmetricpb.ExportMetricsServiceResponse{}, nil
}
