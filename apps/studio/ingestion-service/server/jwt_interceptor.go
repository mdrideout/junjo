package server

import (
	"context"
	"fmt"
	"junjo-server/ingestion-service/jwks"
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
		// Extract the token from the request metadata.
		md, ok := metadata.FromIncomingContext(ctx)
		if !ok {
			return nil, status.Errorf(codes.Unauthenticated, "metadata is not provided")
		}

		values := md["authorization"]
		if len(values) == 0 {
			return nil, status.Errorf(codes.Unauthenticated, "authorization token is not provided")
		}

		// The token is expected to be in the format "Bearer <token>".
		// We take the first element of the slice.
		tokenString := values[0]
		if !strings.HasPrefix(tokenString, "Bearer ") {
			return nil, status.Errorf(codes.Unauthenticated, "invalid token format")
		}
		tokenString = strings.TrimPrefix(tokenString, "Bearer ")

		// Parse the token.
		token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
			// Get the key ID from the token header.
			kid, ok := token.Header["kid"].(string)
			if !ok {
				return nil, fmt.Errorf("kid not found in token header")
			}

			// Get the public key from the JWKS.
			key, err := jwks.GetKey(kid)
			if err != nil {
				return nil, err
			}

			return key, nil
		})
		if err != nil {
			return nil, status.Errorf(codes.Unauthenticated, "invalid token: %v", err)
		}

		if !token.Valid {
			return nil, status.Errorf(codes.Unauthenticated, "invalid token")
		}

		// If the token is valid, call the handler.
		return handler(ctx, req)
	}
}
