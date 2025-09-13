package telemetry

import (
	"fmt"
	"net"
	"os"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"

	"database/sql"

	db "junjo-server/db_gen"    // Import sqlc code
	pb "junjo-server/proto_gen" // Import generated protobuf code

	// Otel imports
	collogspb "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	colmetricpb "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	coltracepb "go.opentelemetry.io/proto/otlp/collector/trace/v1"

	_ "modernc.org/sqlite" // SQLite driver
)

// Proprietary Junjo Services
type server struct {
	pb.UnimplementedNodeLogServiceServer
	pb.UnimplementedWorkflowLogServiceServer
	pb.UnimplementedWorkflowMetadataServiceServer
	queries *db.Queries
}

// NewGRPCServer creates and configures the gRPC server.
func NewGRPCServer(dbConn *sql.DB) (*grpc.Server, net.Listener, error) { // Return listener again
	queries := db.New(dbConn)

	listenAddr := ":50051"
	if port := os.Getenv("GRPC_PORT"); port != "" {
		listenAddr = ":" + port
	}
	lis, err := net.Listen("tcp", listenAddr)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to listen: %v", err)
	}

	// --- Initialize OTLP Services ---
	otelTraceSvc := NewOtelTraceService()

	grpcServer := grpc.NewServer(
		grpc.UnaryInterceptor(ApiKeyAuthInterceptor),
	)

	// Register Proprietary Junjo services
	pb.RegisterNodeLogServiceServer(grpcServer, &server{queries: queries})
	pb.RegisterWorkflowLogServiceServer(grpcServer, &server{queries: queries})
	pb.RegisterWorkflowMetadataServiceServer(grpcServer, &server{queries: queries})

	// Register OTLP services
	coltracepb.RegisterTraceServiceServer(grpcServer, otelTraceSvc) // Pass queries if needed
	colmetricpb.RegisterMetricsServiceServer(grpcServer, &otelMetricService{})
	collogspb.RegisterLogsServiceServer(grpcServer, &otelLogsService{})

	reflection.Register(grpcServer)

	return grpcServer, lis, nil // Return server *and* listener
}
