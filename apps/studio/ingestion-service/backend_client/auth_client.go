package backend_client

import (
	"context"
	"fmt"
	pb "junjo-server/ingestion-service/proto_gen"
	"log"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// AuthClient provides a client for the internal auth service on the backend.
type AuthClient struct {
	conn   *grpc.ClientConn
	client pb.InternalAuthServiceClient
}

// NewAuthClient creates a new gRPC client for the backend's auth service.
func NewAuthClient() (*AuthClient, error) {
	addr := "junjo-server-backend:50053"

	// Use a non-blocking connection. The gRPC client will attempt to connect in the background.
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, err
	}

	return &AuthClient{
		conn:   conn,
		client: pb.NewInternalAuthServiceClient(conn),
	}, nil
}

// Close closes the gRPC connection.
func (c *AuthClient) Close() {
	if c.conn != nil {
		c.conn.Close()
	}
}

// ExchangeApiKeyForJwt calls the backend to exchange an API key for a JWT.
func (c *AuthClient) ExchangeApiKeyForJwt(ctx context.Context, apiKey string) (string, int64, error) {
	req := &pb.ExchangeApiKeyForJwtRequest{
		ApiKey: apiKey,
	}

	var res *pb.ExchangeApiKeyForJwtResponse
	var err error
	backoff := 1 * time.Second
	maxBackoff := 10 * time.Second

	for i := 0; i < 5; i++ { // Retry up to 5 times
		res, err = c.client.ExchangeApiKeyForJwt(ctx, req)
		if err == nil {
			return res.Jwt, res.ExpiresAt, nil
		}

		log.Printf("Failed to exchange API key, retrying in %v: %v", backoff, err)
		time.Sleep(backoff)
		backoff *= 2
		if backoff > maxBackoff {
			backoff = maxBackoff
		}
	}

	return "", 0, fmt.Errorf("failed to exchange API key after multiple retries: %w", err)
}
