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
}

// NewOtelTraceService creates a new trace service.
func NewOtelTraceService() *otelTraceService {
	fmt.Println("Initializing OtelTraceService...")
	s := &otelTraceService{
		receivedSpans: make([]*tracepb.Span, 0),
	}

	fmt.Println("OtelTraceService configured.")

	return s
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
			}
		}
	}

	// Return a response to the client
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
