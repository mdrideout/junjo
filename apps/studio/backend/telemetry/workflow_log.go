package telemetry

import (
	"context"
	"log"

	gonanoid "github.com/matoous/go-nanoid/v2" // Import nanoid package
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/emptypb"

	db "junjo-ui-backend/db_gen"    // Import your sqlc code
	pb "junjo-ui-backend/proto_gen" // Import generated protobuf code

	_ "modernc.org/sqlite" // SQLite driver
)

func (s *server) CreateWorkflowLog(ctx context.Context, req *pb.CreateWorkflowLogRequest) (*emptypb.Empty, error) {
	// Generate a nanoid for the database primary key
	id, err := gonanoid.New()
	if err != nil {
		log.Printf("Error generating ID with nanoid: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to generate ID: %v", err)
	}

	_, err = s.queries.CreateWorkflowLog(ctx, db.CreateWorkflowLogParams{
		ID:            id,
		ExecID:        req.GetExecId(),
		Name:          req.GetName(),
		Type:          req.GetType(),
		EventTimeNano: req.GetEventTimeNano(),
	})
	if err != nil {
		log.Printf("Error creating workflow: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to create workflow: %v", err)
	}
	return &emptypb.Empty{}, nil
}
