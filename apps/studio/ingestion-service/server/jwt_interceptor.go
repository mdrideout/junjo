package server

import (
	"context"
	"fmt"
	"junjo-server/ingestion-service/jwks"
	"log/slog"
	"strings"

	"github.com/golang-jwt/jwt/v5"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

// JWTInterceptor is a gRPC interceptor that validates JWTs.
func JWTInterceptor() grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
		// Bypass JWT validation for the GetToken method.
		if info.FullMethod == "/ingestion.AuthService/GetToken" {
			return handler(ctx, req)
		}

		// Extract the token from the request metadata.
		md, ok := metadata.FromIncomingContext(ctx)
		if !ok {
			slog.Error("JWT validation failed: metadata not provided", "method", info.FullMethod)
			return nil, status.Errorf(codes.Unauthenticated, "metadata is not provided")
		}

		values := md["authorization"]
		if len(values) == 0 {
			slog.Error("JWT validation failed: authorization token not provided", "method", info.FullMethod)
			return nil, status.Errorf(codes.Unauthenticated, "authorization token is not provided")
		}

		// The token is expected to be in the format "Bearer <token>".
		// We take the first element of the slice.
		tokenString := values[0]
		if !strings.HasPrefix(tokenString, "Bearer ") {
			slog.Error("JWT validation failed: invalid token format", "method", info.FullMethod, "token", tokenString)
			return nil, status.Errorf(codes.Unauthenticated, "invalid token format")
		}
		tokenString = strings.TrimPrefix(tokenString, "Bearer ")

		// Parse the token.
		token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
			// Get the key ID from the token header.
			kid, ok := token.Header["kid"].(string)
			if !ok {
				slog.Error("JWT validation failed: kid not found in token header", "method", info.FullMethod, "header", token.Header)
				return nil, fmt.Errorf("kid not found in token header")
			}

			// Get the public key from the JWKS.
			key, err := jwks.GetKey(kid)
			if err != nil {
				slog.Error("JWT validation failed: unable to retrieve key from JWKS", "method", info.FullMethod, "kid", kid, "error", err)
				return nil, err
			}

			return key, nil
		})
		if err != nil {
			slog.Error("JWT validation failed: token parsing error", "method", info.FullMethod, "token", tokenString, "error", err)
			return nil, status.Errorf(codes.Unauthenticated, "invalid token: %v", err)
		}

		if !token.Valid {
			slog.Error("JWT validation failed: token is invalid", "method", info.FullMethod, "token", tokenString)
			return nil, status.Errorf(codes.Unauthenticated, "invalid token")
		}

		// Log successful token validation
		slog.Info("JWT validation successful", "method", info.FullMethod, "kid", token.Header["kid"])

		// If the token is valid, call the handler.
		return handler(ctx, req)
	}
}
