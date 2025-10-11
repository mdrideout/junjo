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
// The connection will automatically reconnect if the backend becomes unavailable.
func NewAuthClient() (*AuthClient, error) {
	addr := "junjo-server-backend:50053"

	// Create a persistent gRPC connection.
	// gRPC automatically manages connection state and reconnects if the backend restarts.
	// The WaitForReady(true) option on individual calls controls whether to wait for
	// the connection to be ready before sending the RPC.
	conn, err := grpc.NewClient(
		addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, err
	}

	log.Printf("Created gRPC client for backend auth service at %s", addr)

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

// ValidateApiKey calls the backend to validate an API key.
// Uses a 5-second timeout for fast failure - if backend is down, this fails quickly
// so the client can retry. The gRPC connection will wait for the backend to be ready
// but respects the timeout to avoid blocking indefinitely.
func (c *AuthClient) ValidateApiKey(ctx context.Context, apiKey string) (bool, error) {
	req := &pb.ValidateApiKeyRequest{
		ApiKey: apiKey,
	}

	// Set a 5-second timeout for this validation call
	// This fails fast if backend is down, allowing the client to retry
	callCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	res, err := c.client.ValidateApiKey(
		callCtx,
		req,
		grpc.WaitForReady(true), // Wait for backend to be ready, but respect timeout
	)
	if err != nil {
		log.Printf("Failed to validate API key with backend: %v", err)
		return false, fmt.Errorf("backend validation failed: %w", err)
	}

	return res.IsValid, nil
}

// WaitUntilReady blocks until the backend is reachable or the context is cancelled.
// This should be called once at startup to ensure the backend is ready before
// accepting traffic.
func (c *AuthClient) WaitUntilReady(ctx context.Context) error {
	log.Println("Waiting for backend gRPC server to be ready...")

	// Try to validate a dummy key - we don't care about the result,
	// just that the backend responds
	req := &pb.ValidateApiKeyRequest{
		ApiKey: "startup-readiness-check",
	}

	_, err := c.client.ValidateApiKey(
		ctx,
		req,
		grpc.WaitForReady(true), // Block until backend is ready
	)
	if err != nil {
		return fmt.Errorf("backend did not become ready: %w", err)
	}

	log.Println("Backend gRPC server is ready!")
	return nil
}
