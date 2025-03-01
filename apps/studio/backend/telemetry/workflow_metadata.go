package telemetry

import (
	"context"
	"encoding/json"
	"log"

	gonanoid "github.com/matoous/go-nanoid/v2" // Import nanoid package
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/emptypb"

	db "junjo-server/db_gen"    // Import your sqlc code
	pb "junjo-server/proto_gen" // Import generated protobuf code

	_ "modernc.org/sqlite" // SQLite driver
)

func (s *server) CreateWorkflowMetadata(ctx context.Context, req *pb.CreateWorkflowMetadataRequest) (*emptypb.Empty, error) {
	// Generate a nanoid for the database primary key
	id, err := gonanoid.New()
	if err != nil {
		log.Printf("Error generating ID with nanoid: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to generate ID: %v", err)
	}

	// Convert the structure JSON string to json.RawMessage
	// This is necessary because we are storing the structure as a JSONB type in the database
	// This is a workaround because the sqlc code generator does not support JSONB types
	// Validate and convert the structure JSON string to json.RawMessage.
	structureStr := req.GetStructure()
	if !json.Valid([]byte(structureStr)) {
		return nil, status.Errorf(codes.InvalidArgument, "invalid JSON provided for structure: %s", structureStr)
	}
	structure := json.RawMessage(structureStr)

	_, err = s.queries.CreateWorkflowMetadata(ctx, db.CreateWorkflowMetadataParams{
		ID:        id,
		ExecID:    req.GetExecId(),
		Name:      req.GetName(),
		Structure: structure,
	})
	if err != nil {
		log.Printf("Error creating workflow_metadata: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to create workflow_metadata: %v", err)
	}
	return &emptypb.Empty{}, nil
}
