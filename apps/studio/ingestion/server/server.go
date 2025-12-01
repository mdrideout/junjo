package server

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"strings"

	"junjo-ai-studio/ingestion/backend_client"
	"junjo-ai-studio/ingestion/config"
	"junjo-ai-studio/ingestion/storage"

	grpc_logging "github.com/grpc-ecosystem/go-grpc-middleware/v2/interceptors/logging"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"

	// Otel imports
	pb "junjo-ai-studio/ingestion/proto_gen"

	collogspb "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	colmetricpb "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	coltracepb "go.opentelemetry.io/proto/otlp/collector/trace/v1"
)

// NewGRPCServer creates and configures the gRPC server for the ingestion service.
func NewGRPCServer(repo storage.SpanRepository, authClient *backend_client.AuthClient) (*grpc.Server, net.Listener, error) {
	cfg := config.Get().Server
	listenAddr := ":" + cfg.PublicPort
	lis, err := net.Listen("tcp", listenAddr)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to listen: %v", err)
	}

	// --- Initialize Services ---
	otelTraceSvc := NewOtelTraceService(repo)
	otelLogsSvc := NewOtelLogsService()
	otelMetricSvc := NewOtelMetricService()

	grpcServer := grpc.NewServer(
		grpc.ChainUnaryInterceptor(
			grpc_logging.UnaryServerInterceptor(
				interceptorLogger(),
				grpc_logging.WithLogOnEvents(
					grpc_logging.StartCall,
					grpc_logging.FinishCall,
				),
			),
			ApiKeyAuthInterceptor(authClient),
		),
	)

	// Register services
	coltracepb.RegisterTraceServiceServer(grpcServer, otelTraceSvc)
	colmetricpb.RegisterMetricsServiceServer(grpcServer, otelMetricSvc)
	collogspb.RegisterLogsServiceServer(grpcServer, otelLogsSvc)

	reflection.Register(grpcServer)

	return grpcServer, lis, nil
}

// NewInternalGRPCServer creates a new gRPC server for internal services.
func NewInternalGRPCServer(repo storage.SpanRepository, flusher *storage.Flusher) (*grpc.Server, net.Listener, error) {
	cfg := config.Get().Server
	listenAddr := ":" + cfg.InternalPort
	lis, err := net.Listen("tcp", listenAddr)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to listen on internal port: %v", err)
	}

	// --- Initialize Internal Services ---
	walReaderSvc := NewWALReaderService(repo, flusher)

	// Custom logging function that checks method name
	logFunc := func(ctx context.Context, lvl grpc_logging.Level, msg string, fields ...any) {
		// Extract method name from fields
		var isHealthCheck bool
		for i := 0; i < len(fields); i += 2 {
			if i+1 < len(fields) {
				if key, ok := fields[i].(string); ok && key == "grpc.service" {
					if service, ok := fields[i+1].(string); ok && strings.Contains(service, "grpc.health") {
						isHealthCheck = true
						break
					}
				}
			}
		}

		// Log health checks at DEBUG level, everything else at original level
		if isHealthCheck {
			slog.Log(ctx, slog.LevelDebug, msg, fields...)
		} else {
			slog.Log(ctx, slog.Level(lvl), msg, fields...)
		}
	}

	grpcServer := grpc.NewServer(
		grpc.UnaryInterceptor(
			grpc_logging.UnaryServerInterceptor(
				grpc_logging.LoggerFunc(logFunc),
				grpc_logging.WithLogOnEvents(grpc_logging.FinishCall),
			),
		),
	)

	// Register Internal services
	pb.RegisterInternalIngestionServiceServer(grpcServer, walReaderSvc)

	// Register health server for grpc_health_probe
	healthServer := health.NewServer()
	healthpb.RegisterHealthServer(grpcServer, healthServer)

	reflection.Register(grpcServer)

	return grpcServer, lis, nil
}

// interceptorLogger returns a grpc_logging.Logger that uses the global slog.
func interceptorLogger() grpc_logging.Logger {
	return grpc_logging.LoggerFunc(func(ctx context.Context, lvl grpc_logging.Level, msg string, fields ...any) {
		slog.Log(ctx, slog.Level(lvl), msg, fields...)
	})
}
