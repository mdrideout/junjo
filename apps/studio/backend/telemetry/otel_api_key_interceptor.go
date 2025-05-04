package telemetry

import (
	"context"
	"database/sql"          // Needed for sql.ErrNoRows
	"junjo-server/api_keys" // Import your api_keys repository
	"log"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

// ApiKeyAuthInterceptor checks for a valid API key in the request metadata.
func ApiKeyAuthInterceptor(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
	// Log the incoming request
	log.Printf("Auth Interceptor: Received request for method: %s", info.FullMethod)

	md, ok := metadata.FromIncomingContext(ctx)
	if !ok {
		log.Println("Auth Interceptor: Missing metadata")
		return nil, status.Errorf(codes.Unauthenticated, "missing metadata")
	}

	// Check for the API key header (adjust key name if you used something else)
	apiKeys := md.Get("x-api-key")
	if len(apiKeys) == 0 {
		log.Println("Auth Interceptor: Missing x-api-key header")
		return nil, status.Errorf(codes.Unauthenticated, "API key is required")
	}

	apiKey := apiKeys[0]
	if apiKey == "" {
		log.Println("Auth Interceptor: Empty x-api-key header")
		return nil, status.Errorf(codes.Unauthenticated, "API key cannot be empty")
	}

	// Validate the API key against the database
	_, err := api_keys.GetAPIKey(ctx, apiKey)
	if err != nil {
		if err == sql.ErrNoRows {
			log.Printf("Auth Interceptor: Invalid API key provided: %s", apiKey)
			return nil, status.Errorf(codes.Unauthenticated, "invalid API key")
		}
		// Handle other potential database errors
		log.Printf("Auth Interceptor: Error validating API key: %v", err)
		return nil, status.Errorf(codes.Internal, "error validating API key")
	}

	// API key is valid, proceed with the original handler
	log.Printf("Auth Interceptor: API Key validated successfully for key starting with: %s...", apiKey[:min(8, len(apiKey))])
	return handler(ctx, req)
}

// Helper function to avoid index out of range
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
