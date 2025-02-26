package telemetry

import (
	"context"
	"log"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/emptypb"

	db "junjo-ui-backend/db_gen"    // Import your sqlc code
	pb "junjo-ui-backend/proto_gen" // Import generated protobuf code

	_ "modernc.org/sqlite" // SQLite driver
)

func (s *server) CreateWorkflow(ctx context.Context, req *pb.CreateWorkflowRequest) (*emptypb.Empty, error) {
	_, err := s.queries.CreateWorkflow(ctx, db.CreateWorkflowParams{
		ID:   req.GetId(),
		Name: req.GetName(),
	})
	if err != nil {
		log.Printf("Error creating workflow: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to create workflow: %v", err)
	}
	return &emptypb.Empty{}, nil
}
