package otel_token

import (
	"context"
	"junjo-server/db"
	"junjo-server/db_gen"
	"junjo-server/jwks"
	"net/http"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/labstack/echo/v4"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Claims represents the JWT claims structure
type Claims struct {
	APIKeyID string `json:"api_key_id"`
	jwt.RegisteredClaims
}

// createOtelTokenLogic contains the core logic for creating a JWT from an API key.
// It's unexported and returns standard errors for reusability.
func createOtelTokenLogic(apiKey string) (string, time.Time, error) {
	// Validate the API key against the database
	queries := db_gen.New(db.DB)
	apiKeyRecord, err := queries.GetAPIKey(context.Background(), apiKey)
	if err != nil {
		return "", time.Time{}, status.Errorf(codes.Unauthenticated, "invalid API key")
	}

	// Define expiration
	expirationTime := time.Now().Add(time.Hour)

	// Create the claims
	claims := &Claims{
		APIKeyID: apiKeyRecord.ID,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(expirationTime),
			Issuer:    "junjo-server-backend",
		},
	}

	// Create and sign the token
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	token.Header["kid"] = "1"
	privateKey := jwks.GetPrivateKey()
	tokenString, err := token.SignedString(privateKey)
	if err != nil {
		return "", time.Time{}, status.Errorf(codes.Internal, "failed to sign token")
	}

	return tokenString, expirationTime, nil
}

// CreateOTelJWT is the handler for the HTTP endpoint.
// It wraps the core logic and returns an echo.HTTPError on failure.
func CreateOTelJWT(apiKey string) (string, error) {
	tokenString, _, err := createOtelTokenLogic(apiKey)
	if err != nil {
		// Convert gRPC status errors to HTTP errors for the HTTP endpoint
		if s, ok := status.FromError(err); ok {
			switch s.Code() {
			case codes.Unauthenticated:
				return "", echo.NewHTTPError(http.StatusUnauthorized, s.Message())
			default:
				return "", echo.NewHTTPError(http.StatusInternalServerError, s.Message())
			}
		}
		return "", echo.NewHTTPError(http.StatusInternalServerError, "an unexpected error occurred")
	}
	return tokenString, nil
}
