package telemetry

import (
	"context"
	"log"
	"time"

	coltracepb "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// JaegerForwarder handles forwarding OTLP trace data to a Jaeger collector.
type JaegerForwarder struct {
	conn   *grpc.ClientConn
	client coltracepb.TraceServiceClient
}

// NewJaegerForwarder creates and initializes a JaegerForwarder.
// It attempts to connect to the provided Jaeger OTLP gRPC endpoint.
// If endpoint is empty or connection fails, it returns a nil forwarder without error,
// logging a warning instead.
func NewJaegerForwarder(endpoint string) *JaegerForwarder {
	if endpoint == "" {
		log.Println("Jaeger OTLP gRPC endpoint not provided, forwarding disabled.")
		return nil // Return nil, indicating no forwarding
	}

	log.Printf("Initializing Jaeger OTLP gRPC forwarder for endpoint: %s", endpoint)
	conn, err := grpc.NewClient(endpoint,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		// Consider adding grpc.WithBlock() and a timeout during startup
		// if you want to ensure connection before proceeding.
	)
	if err != nil {
		log.Printf("WARNING: Failed to connect to Jaeger forwarder endpoint %s: %v. Forwarding disabled.", endpoint, err)
		return nil // Return nil on connection error
	}

	log.Printf("Successfully connected Jaeger OTLP gRPC forwarder to: %s", endpoint)
	return &JaegerForwarder{
		conn:   conn,
		client: coltracepb.NewTraceServiceClient(conn),
	}
}

// ForwardTraces sends the trace request to the configured Jaeger collector.
// It handles context deadlines and logs errors internally.
func (jf *JaegerForwarder) ForwardTraces(ctx context.Context, req *coltracepb.ExportTraceServiceRequest) {
	if jf == nil || jf.client == nil {
		// Should not happen if initialized correctly, but safe check.
		log.Println("Jaeger forwarder not initialized, skipping forward.")
		return
	}

	// Use a timeout context for the forwarding call, derived from the original if possible,
	// or a background context with a specific timeout.
	forwardCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second) // Adjust timeout as needed
	defer cancel()

	log.Printf("Forwarding %d ResourceSpans to Jaeger via forwarder...", len(req.ResourceSpans))
	_, err := jf.client.Export(forwardCtx, req) // Pass the original request object
	if err != nil {
		// Log forwarding error. Consider adding metrics or more robust error handling.
		log.Printf("ERROR: Jaeger Forwarder failed to send traces: %v", err)
	} else {
		log.Printf("Jaeger Forwarder successfully sent %d ResourceSpans.", len(req.ResourceSpans))
	}
}

// Close cleanly shuts down the gRPC connection to Jaeger.
func (jf *JaegerForwarder) Close() error {
	if jf != nil && jf.conn != nil {
		log.Println("Closing Jaeger forwarder connection...")
		return jf.conn.Close()
	}
	return nil
}
