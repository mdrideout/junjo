package otel_token

import (
	"net/http"

	"github.com/labstack/echo/v4"
)

// HandleOTelTokenRequest handles requests for OTel JWT tokens
func HandleOTelTokenRequest(c echo.Context) error {
	// Extract API key from request (assuming it's in the Authorization header)
	apiKey := c.Request().Header.Get("Authorization")
	if len(apiKey) < 7 || apiKey[:7] != "Bearer " {
		return echo.NewHTTPError(http.StatusUnauthorized, "Invalid authorization header")
	}
	apiKey = apiKey[7:] // Remove "Bearer " prefix

	// Create and return the JWT
	tokenString, err := CreateOTelJWT(apiKey)
	if err != nil {
		return err
	}

	return c.JSON(http.StatusOK, OTelTokenResponse{Token: tokenString})
}
