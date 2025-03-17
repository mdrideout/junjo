package telemetry

import (
	"context"
	"fmt"
	"sync"

	collogspb "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	logspb "go.opentelemetry.io/proto/otlp/logs/v1"
)

type otelLogsService struct {
	collogspb.UnimplementedLogsServiceServer                     // Embed for forward compatibility
	mu                                       sync.Mutex          // Protects the receivedLogs slice
	receivedLogs                             []*logspb.LogRecord // Store received logs
}

// Export handles the incoming logs.
func (s *otelLogsService) Export(ctx context.Context, req *collogspb.ExportLogsServiceRequest) (*collogspb.ExportLogsServiceResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	for _, resourceLogs := range req.ResourceLogs {
		for _, scopeLogs := range resourceLogs.ScopeLogs {
			for _, logRecord := range scopeLogs.LogRecords {
				s.receivedLogs = append(s.receivedLogs, logRecord)
				fmt.Printf("OTel Log Service: Received Log: %s\n", logRecord.Body.GetStringValue()) //Log the span details
				fmt.Printf("IS JUNJO EVEN SETUP TO SEND LOGS YET?")
			}
		}
	}
	return &collogspb.ExportLogsServiceResponse{}, nil
}
