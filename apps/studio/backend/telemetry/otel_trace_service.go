package telemetry

import (
	"context"
	"encoding/hex"
	"fmt"
	"sync"

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
		// Get the service name
		serviceName := getServiceName(resourceSpans)
		fmt.Printf("\nReceived ResourceSpans for Service: %s\n", serviceName)
		for _, scopeSpans := range resourceSpans.ScopeSpans {
			for _, span := range scopeSpans.Spans {
				s.receivedSpans = append(s.receivedSpans, span)
				traceID := hex.EncodeToString(span.TraceId)
				spanID := hex.EncodeToString(span.SpanId)
				fmt.Printf("Received Span ID: %s, Trace ID: %s, Name: %s\n", spanID, traceID, span.Name)

				// Pass the *protobuf* span directly to the processing function.
				if err := ProcessSpan(ctx, serviceName, span); err != nil {
					fmt.Printf("OTel Trace Service: Error processing span: %v\n", err)
				}

				// spanJSON, err := json.MarshalIndent(span, "", "  ")
				// if err != nil {
				// 	fmt.Printf("OTel Trace Service: Error marshaling span to JSON: %v\n", err)
				// 	continue
				// }
				// fmt.Printf("OTel Trace Service: Received Span:\n%s\n", spanJSON)

				// // Example of storing to a database (assuming you have a queries object):
				// // _, err := s.queries.CreateSpan(ctx, db.CreateSpanParams{...})
				// // if err != nil { ... handle error ... }
			}
		}
	}
	return &coltracepb.ExportTraceServiceResponse{}, nil
}

// getServiceName extracts the service.name from the Resource, handling nil cases.
func getServiceName(resource *tracepb.ResourceSpans) string {
	if resource == nil {
		return "<unknown service>" // Or return an empty string, or handle as needed
	}

	for _, attr := range resource.Resource.Attributes {
		if attr.Key == "service.name" {
			// Use helper function
			return attr.Value.GetStringValue()
		}
	}
	return "<unknown service>" // Or handle as needed (e.g., log an error)
}
