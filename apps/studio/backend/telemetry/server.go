package telemetry

import (
	"fmt"
	"net"
	"os"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"

	"database/sql"

	db "junjo-server/db_gen"    // Import your sqlc code
	pb "junjo-server/proto_gen" // Import generated protobuf code

	_ "modernc.org/sqlite" // SQLite driver
)

type server struct {
	pb.UnimplementedNodeLogServiceServer
	pb.UnimplementedWorkflowLogServiceServer
	pb.UnimplementedWorkflowMetadataServiceServer
	queries *db.Queries
}

// NewGRPCServer creates and configures the gRPC server.
func NewGRPCServer(dbConn *sql.DB) (*grpc.Server, net.Listener, error) { // Return listener again
	queries := db.New(dbConn)

	listenAddr := ":50051" // Default gRPC port
	if port := os.Getenv("GRPC_PORT"); port != "" {
		listenAddr = ":" + port
	}
	lis, err := net.Listen("tcp", listenAddr)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer()

	// Register services
	pb.RegisterNodeLogServiceServer(grpcServer, &server{queries: queries})
	pb.RegisterWorkflowLogServiceServer(grpcServer, &server{queries: queries})
	pb.RegisterWorkflowMetadataServiceServer(grpcServer, &server{queries: queries})
	reflection.Register(grpcServer)

	return grpcServer, lis, nil // Return server *and* listener
}
