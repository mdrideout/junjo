package internal_auth

import (
	"context"
	"database/sql"
	"junjo-server/api_keys"
	pb "junjo-server/proto_gen"
	"log/slog"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// InternalAuthService implements the gRPC server for internal authentication.
type InternalAuthService struct {
	pb.UnimplementedInternalAuthServiceServer
}

// NewInternalAuthService creates a new InternalAuthService.
func NewInternalAuthService() *InternalAuthService {
	return &InternalAuthService{}
}

// ValidateApiKey checks if an API key is valid.
func (s *InternalAuthService) ValidateApiKey(ctx context.Context, req *pb.ValidateApiKeyRequest) (*pb.ValidateApiKeyResponse, error) {
	slog.Info("Validating API key", "received_key", req.ApiKey)
	_, err := api_keys.GetAPIKey(ctx, req.ApiKey)
	if err != nil {
		if err == sql.ErrNoRows {
			return &pb.ValidateApiKeyResponse{IsValid: false}, nil
		}
		return nil, status.Errorf(codes.Internal, "failed to get API key: %v", err)
	}

	// Key is valid, return success
	return &pb.ValidateApiKeyResponse{
		IsValid: true,
	}, nil
}
