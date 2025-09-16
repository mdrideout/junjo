package otel_token

import (
	"context"
	pb "junjo-server/proto_gen"
)

// InternalAuthService implements the gRPC server for internal authentication.
type InternalAuthService struct {
	pb.UnimplementedInternalAuthServiceServer
}

// NewInternalAuthService creates a new InternalAuthService.
func NewInternalAuthService() *InternalAuthService {
	return &InternalAuthService{}
}

// ExchangeApiKeyForJwt validates an API key and returns a signed JWT.
func (s *InternalAuthService) ExchangeApiKeyForJwt(ctx context.Context, req *pb.ExchangeApiKeyForJwtRequest) (*pb.ExchangeApiKeyForJwtResponse, error) {
	jwt, expiresAt, err := createOtelTokenLogic(req.ApiKey)
	if err != nil {
		return nil, err
	}

	return &pb.ExchangeApiKeyForJwtResponse{
		Jwt:       jwt,
		ExpiresAt: expiresAt.Unix(),
	}, nil
}
