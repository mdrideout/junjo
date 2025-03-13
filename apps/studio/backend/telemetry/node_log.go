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

func (s *server) CreateNodeLog(ctx context.Context, req *pb.CreateNodeLogRequest) (*emptypb.Empty, error) {
	// Generate a nanoid for the database primary key
	id, err := gonanoid.New()
	if err != nil {
		log.Printf("Error generating ID with nanoid: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to generate ID: %v", err)
	}

	// Convert the state JSON string to json.RawMessage
	// This is necessary because we are storing the state as a JSONB type in the database
	// This is a workaround because the sqlc code generator does not support JSONB types
	// Validate and convert the state JSON string to json.RawMessage.
	stateStr := req.GetState()
	if !json.Valid([]byte(stateStr)) {
		return nil, status.Errorf(codes.InvalidArgument, "invalid JSON provided for state: %s", stateStr)
	}
	state := json.RawMessage(stateStr)

	_, err = s.queries.CreateNodeLog(ctx, db.CreateNodeLogParams{
		ID:            id,
		ExecID:        req.GetExecId(),
		Type:          req.GetType(),
		EventTimeNano: req.GetEventTimeNano(),
		State:         state,
	})
	if err != nil {
		log.Printf("Error creating workflow_log: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to create workflow_log: %v", err)
	}
	return &emptypb.Empty{}, nil
}

// TRANSACTION EXAMPLE
// func (s *server) CreateNodeLog(ctx context.Context, req *pb.CreateNodeLogRequest) (*emptypb.Empty, error) {
// 	tx, err := DB.DB.BeginTx(ctx, nil)
// 	if err != nil {
// 		log.Printf("Error starting node log transaction: %v", err)
// 		return nil, status.Errorf(codes.Internal, "failed to start transaction: %v", err)
// 	}
// 	// Defer rollback in case of error
// 	defer func() {
// 		if rErr := tx.Rollback(); rErr != nil && rErr != sql.ErrTxDone { // Check if rollback error is not ErrTxDone
// 			log.Printf("Error rolling back transaction: %v", rErr)
// 		}
// 	}()

// 	// Create a new Queries object that uses the transaction
// 	qtx := s.queries.WithTx(tx)

// 	// Generate a nanoid for the database primary key
// 	id, err := gonanoid.New()
// 	if err != nil {
// 		log.Printf("Error generating ID with nanoid: %v", err)
// 		return nil, status.Errorf(codes.Internal, "failed to generate ID: %v", err)
// 	}

// 	// Convert the state JSON string to json.RawMessage
// 	// This is necessary because we are storing the state as a JSONB type in the database
// 	// This is a workaround because the sqlc code generator does not support JSONB types
// 	// Validate and convert the state JSON string to json.RawMessage.
// 	stateStr := req.GetState()
// 	if !json.Valid([]byte(stateStr)) {
// 		return nil, status.Errorf(codes.InvalidArgument, "invalid JSON provided for state: %s", stateStr)
// 	}
// 	state := json.RawMessage(stateStr)

// 	_, err = qtx.CreateNodeLog(ctx, db.CreateNodeLogParams{
// 		ID:            id,
// 		ExecID:        req.GetExecId(),
// 		Type:          req.GetType(),
// 		EventTimeNano: req.GetEventTimeNano(),
// 		State:         state,
// 	})
// 	if err != nil {
// 		// Rollback the transaction on error
// 		if rErr := tx.Rollback(); rErr != nil && rErr != sql.ErrTxDone { // Redundant rollback, already deferred, but good practice
// 			log.Printf("Error rolling back transaction after CreateNodeLog failure: %v, original error: %v", rErr, err)
// 		}
// 		log.Printf("Error creating node_log within transaction: %v", err)
// 		return nil, status.Errorf(codes.Internal, "failed to create node_log: %v", err)
// 	}

// 	// Commit the transaction
// 	if err := tx.Commit(); err != nil {
// 		log.Printf("Error committing transaction: %v", err)
// 		return nil, status.Errorf(codes.Internal, "failed to commit transaction: %v", err)
// 	}

// 	log.Printf("Created node_log (transactional): %v", id)
// 	return &emptypb.Empty{}, nil
// }
