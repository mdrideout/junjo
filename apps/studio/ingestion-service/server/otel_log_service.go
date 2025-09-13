package server

import (
	"context"
	"log"

	collogspb "go.opentelemetry.io/proto/otlp/collector/logs/v1"
)

type OtelLogsService struct {
	collogspb.UnimplementedLogsServiceServer // Embed for forward compatibility
}

// NewOtelLogsService creates a new logs service.
func NewOtelLogsService() *OtelLogsService {
	return &OtelLogsService{}
}

// Export handles the incoming logs.
func (s *OtelLogsService) Export(ctx context.Context, req *collogspb.ExportLogsServiceRequest) (*collogspb.ExportLogsServiceResponse, error) {
	// For now, we just log that we received logs.
	// In the future, these could also be written to the WAL.
	log.Printf("Received %d resource logs", len(req.ResourceLogs))
	return &collogspb.ExportLogsServiceResponse{}, nil
}
