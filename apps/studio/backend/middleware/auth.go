package middleware

import (
	"net/http"

	"junjo-server/auth"

	"github.com/labstack/echo/v4"
)

// Auth Routes To Skip
var authRoutesToSkip = []string{"/ping", "/sign-in", "/csrf", "/users/create-first-user", "/users/db-has-users", "/.well-known/jwks.json"}

// Auth is a middleware function that checks for a valid session.
func Auth() echo.MiddlewareFunc {
	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			// --- Check for Skipped Routes ---
			for _, route := range authRoutesToSkip {
				if c.Path() == route {
					return next(c) // Skip authentication
				}
			}

			// --- Check for Session ---
			userEmail, err := auth.GetUserEmailFromSession(c) // Use the GetUserEmailFromSession function
			if err != nil {
				// No valid session.  Return an unauthorized error.
				return echo.NewHTTPError(http.StatusUnauthorized, "Unauthorized: No valid session")
			}

			// --- Session is Valid: Set User ID in Context ---
			c.Set("userEmail", userEmail) // Set the user ID (email in this case) in the context
			return next(c)
		}
	}
}
