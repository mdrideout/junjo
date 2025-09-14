package otel_token

import (
	"context"
	"junjo-server/db"
	"junjo-server/db_gen"
	"junjo-server/jwks"
	"net/http"
	"os"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/labstack/echo/v4"
)

// Claims represents the JWT claims structure
type Claims struct {
	APIKeyID int64 `json:"api_key_id"`
	jwt.RegisteredClaims
}

// CreateOTelJWT creates a new JWT for OTel exporters
func CreateOTelJWT(apiKey string) (string, error) {
	// Validate the API key against the database
	queries := db_gen.New(db.DB) // Assuming db.DB is your database connection
	apiKeyRecord, err := queries.GetAPIKey(context.Background(), apiKey)
	if err != nil {
		return "", echo.NewHTTPError(http.StatusUnauthorized, "Invalid API key")
	}

	// Fetch the JWT secret from environment variables
	jwtSecret := os.Getenv("JUNJO_JWT_SECRET")
	if jwtSecret == "" {
		return "", echo.NewHTTPError(http.StatusInternalServerError, "JWT secret not configured")
	}

	// Create the claims
	claims := &Claims{
		APIKeyID: apiKeyRecord.ID,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)), // 1 hour expiration
			Issuer:    "junjo-server-backend",
		},
	}

	// Create the token
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)

	// Sign the token
	privateKey := jwks.GetPrivateKey()
	tokenString, err := token.SignedString(privateKey)
	if err != nil {
		return "", echo.NewHTTPError(http.StatusInternalServerError, "Failed to sign token")
	}

	return tokenString, nil
}
