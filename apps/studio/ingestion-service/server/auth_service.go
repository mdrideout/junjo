package server

import (
	"context"
	"junjo-server/ingestion-service/backend_client"
	pb "junjo-server/ingestion-service/proto_gen"
)

// AuthService implements the gRPC server for public authentication.
type AuthService struct {
	pb.UnimplementedAuthServiceServer
	BackendClient *backend_client.AuthClient
}

// NewAuthService creates a new AuthService.
func NewAuthService(backendClient *backend_client.AuthClient) *AuthService {
	return &AuthService{BackendClient: backendClient}
}

// GetToken handles the public-facing request to exchange an API key for a JWT.
func (s *AuthService) GetToken(ctx context.Context, req *pb.GetTokenRequest) (*pb.GetTokenResponse, error) {
	jwt, expiresAt, err := s.BackendClient.ExchangeApiKeyForJwt(ctx, req.ApiKey)
	if err != nil {
		return nil, err
	}

	return &pb.GetTokenResponse{
		Jwt:       jwt,
		ExpiresAt: expiresAt,
	}, nil
}
