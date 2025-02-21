package middlware

import (
	"log"
	"net/http"
	"strings"

	"junjo-ui-backend/auth"

	"github.com/labstack/echo/v4"
)

// Auth Routes To Skip
var authRoutesToSkip = []string{"/ping", "/sign-in"}

// Auth is a middleware function that verifies the ID token in the Authorization header
func Auth() echo.MiddlewareFunc {
	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			// Check if the current route should be skipped
			for _, route := range authRoutesToSkip {
				if c.Path() == route {
					// Log the excluded route
					log.Printf("SKIPPING AUTH FOR: %s\n", route)
					return next(c) // Skip authentication and proceed
				}
			}

			// Get token from header
			authHeader := c.Request().Header.Get("Authorization")
			if authHeader == "" {
				return echo.NewHTTPError(http.StatusUnauthorized, "missing authorization header")
			}

			// Remove "Bearer " prefix
			tokenString := strings.TrimPrefix(authHeader, "Bearer ")

			// Validate token
			claims, err := auth.ValidateJWT(tokenString)
			if err != nil {
				log.Printf("failed to validate token: %v", err)
				return echo.NewHTTPError(http.StatusUnauthorized, "token validation failed")
			}

			// Set claims in context
			c.Set("user", claims)

			return next(c)
		}
	}
}
