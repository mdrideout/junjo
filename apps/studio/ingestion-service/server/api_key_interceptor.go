package server

import (
	"context"
	"junjo-server/ingestion-service/backend_client"
	"log/slog"
	"time"

	"github.com/maypok86/otter/v2"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

// ApiKeyAuthInterceptor is a gRPC interceptor that validates static API keys.
func ApiKeyAuthInterceptor(authClient *backend_client.AuthClient) grpc.UnaryServerInterceptor {
	// Initialize a new cache with a capacity of 10,000 keys and a 1-hour TTL.
	cache := otter.Must(&otter.Options[string, bool]{
		MaximumSize:      10_000,
		ExpiryCalculator: otter.ExpiryWriting[string, bool](time.Hour),
	})

	return func(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
		md, ok := metadata.FromIncomingContext(ctx)
		if !ok {
			slog.Error("API key validation failed: metadata not provided", "method", info.FullMethod)
			return nil, status.Errorf(codes.Unauthenticated, "metadata is not provided")
		}

		values := md["x-junjo-api-key"]
		if len(values) == 0 {
			slog.Error("API key validation failed: x-junjo-api-key not provided", "method", info.FullMethod)
			return nil, status.Errorf(codes.Unauthenticated, "x-junjo-api-key is not provided")
		}
		apiKey := values[0]

		// Check the cache first.
		if _, ok := cache.GetIfPresent(apiKey); ok {
			slog.Info("API key validation successful (from cache)", "method", info.FullMethod)
			return handler(ctx, req)
		}

		// If not in cache, validate with the backend.
		isValid, err := authClient.ValidateApiKey(ctx, apiKey)
		if err != nil {
			slog.Error("API key validation failed: backend validation error", "method", info.FullMethod, "error", err)
			return nil, status.Errorf(codes.Internal, "failed to validate API key")
		}

		if !isValid {
			slog.Error("API key validation failed: invalid API key", "method", info.FullMethod)
			return nil, status.Errorf(codes.Unauthenticated, "invalid API key")
		}

		// Store the valid key in the cache.
		cache.Set(apiKey, true)
		slog.Info("API key validation successful (from backend)", "method", info.FullMethod)

		return handler(ctx, req)
	}
}
