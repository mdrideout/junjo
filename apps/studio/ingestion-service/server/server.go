package server

import (
	"fmt"
	"net"
	"os"

	"junjo-server/ingestion-service/storage"

	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"

	// Otel imports
	pb "junjo-server/ingestion-service/proto_gen"

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

	grpcServer := grpc.NewServer(
		grpc.UnaryInterceptor(JWTInterceptor()),
	)

	// Register OTLP services
	coltracepb.RegisterTraceServiceServer(grpcServer, otelTraceSvc)
	colmetricpb.RegisterMetricsServiceServer(grpcServer, otelMetricSvc)
	collogspb.RegisterLogsServiceServer(grpcServer, otelLogsSvc)

	reflection.Register(grpcServer)

	return grpcServer, lis, nil
}

// NewInternalGRPCServer creates a new gRPC server for internal services.
func NewInternalGRPCServer(store *storage.Storage) (*grpc.Server, net.Listener, error) {
	listenAddr := ":50052" // Default internal port
	lis, err := net.Listen("tcp", listenAddr)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to listen on internal port: %v", err)
	}

	// --- Initialize Internal Services ---
	walReaderSvc := NewWALReaderService(store)

	grpcServer := grpc.NewServer()

	// Register Internal services
	pb.RegisterInternalIngestionServiceServer(grpcServer, walReaderSvc)

	// Register health server for grpc_health_probe
	healthServer := health.NewServer()
	healthpb.RegisterHealthServer(grpcServer, healthServer)

	reflection.Register(grpcServer)

	return grpcServer, lis, nil
}
