package telemetry

import (
	"context"
	"fmt"
	"sync"

	"go.opentelemetry.io/otel/trace"
	coltracepb "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

type otelTraceService struct {
	coltracepb.UnimplementedTraceServiceServer
	mu            sync.Mutex // Protect shared data
	receivedSpans []*tracepb.Span
	// You can add a database connection here if you want to store spans:
	// queries *db.Queries
}

func (s *otelTraceService) Export(ctx context.Context, req *coltracepb.ExportTraceServiceRequest) (*coltracepb.ExportTraceServiceResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	for _, resourceSpans := range req.ResourceSpans {
		for _, scopeSpans := range resourceSpans.ScopeSpans {
			for _, span := range scopeSpans.Spans {
				s.receivedSpans = append(s.receivedSpans, span)
				traceID := trace.TraceID(span.TraceId)
				fmt.Printf("OTel Trace Service: Received Span: %s, Trace ID: %s\n", span.Name, traceID)

				// spanJSON, err := json.MarshalIndent(span, "", "  ")
				// if err != nil {
				// 	fmt.Printf("OTel Trace Service: Error marshaling span to JSON: %v\n", err)
				// 	continue
				// }
				// fmt.Printf("OTel Trace Service: Received Span:\n%s\n", spanJSON)

				// Pass the *protobuf* span directly to the processing function.
				if err := ProcessSpan(ctx, span); err != nil {
					fmt.Printf("OTel Trace Service: Error processing span: %v\n", err)
					//  Log the error, perhaps add metrics for failed spans, etc.
				}

				// // Example of storing to a database (assuming you have a queries object):
				// // _, err := s.queries.CreateSpan(ctx, db.CreateSpanParams{...})
				// // if err != nil { ... handle error ... }
			}
		}
	}
	return &coltracepb.ExportTraceServiceResponse{}, nil
}
