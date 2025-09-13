package server

import (
	"fmt"
	"net"
	"os"

	"junjo-server/ingestion-service/storage"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"

	// Otel imports
	collogspb "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	colmetricpb "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	coltracepb "go.opentelemetry.io/proto/otlp/collector/trace/v1"
)

// NewGRPCServer creates and configures the gRPC server for the ingestion service.
func NewGRPCServer(store *storage.Storage) (*grpc.Server, net.Listener, error) {
	listenAddr := ":50051"
	if port := os.Getenv("GRPC_PORT"); port != "" {
		listenAddr = ":" + port
	}
	lis, err := net.Listen("tcp", listenAddr)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to listen: %v", err)
	}

	// --- Initialize OTLP Services ---
	otelTraceSvc := NewOtelTraceService(store)
	otelLogsSvc := NewOtelLogsService()
	otelMetricSvc := NewOtelMetricService()

	// TODO: Add back the API Key interceptor
	grpcServer := grpc.NewServer()

	// Register OTLP services
	coltracepb.RegisterTraceServiceServer(grpcServer, otelTraceSvc)
	colmetricpb.RegisterMetricsServiceServer(grpcServer, otelMetricSvc)
	collogspb.RegisterLogsServiceServer(grpcServer, otelLogsSvc)

	reflection.Register(grpcServer)

	return grpcServer, lis, nil
}
