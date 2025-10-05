package api_keys

import (
	"database/sql"
	"junjo-server/db_gen"
	"net/http"

	"github.com/labstack/echo/v4"
	gonanoid "github.com/matoous/go-nanoid/v2"
)

// generateSecureKey creates a cryptographically secure random alphanumeric string using nanoid.
func generateSecureKey(length int) (string, error) {
	// Define the alphabet for alphanumeric characters
	alphanumeric := "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
	// Create a nanoid generator function with the specified alphabet and length
	key, err := gonanoid.Generate(alphanumeric, length)
	if err != nil {
		return "", err // Return error if generator creation fails
	}
	return key, nil
}

// HandleCreateAPIKey handles the creation of a new API key.
func HandleCreateAPIKey(c echo.Context) error {
	var req CreateAPIKeyRequest
	if err := c.Bind(&req); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, "Invalid request body: "+err.Error())
	}
	if err := c.Validate(&req); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, "Validation failed: "+err.Error())
	}

	newKey, err := generateSecureKey(64)
	if err != nil {
		c.Logger().Error("Failed to generate secure API key:", err)
		return echo.NewHTTPError(http.StatusInternalServerError, "Failed to generate API key")
	}

	newID, err := gonanoid.New()
	if err != nil {
		c.Logger().Error("Failed to generate new ID:", err)
		return echo.NewHTTPError(http.StatusInternalServerError, "Failed to generate new ID")
	}

	apiKey, err := CreateAPIKey(c.Request().Context(), newID, newKey, req.Name)
	if err != nil {
		c.Logger().Error("Failed to create API key in database:", err)
		return echo.NewHTTPError(http.StatusInternalServerError, "Failed to save API key")
	}

	return c.JSON(http.StatusCreated, apiKey)
}

// HandleListAPIKeys handles listing all API keys.
func HandleListAPIKeys(c echo.Context) error {
	apiKeys, err := ListAPIKeys(c.Request().Context())
	if err != nil {
		c.Logger().Error("Failed to list API keys:", err)
		return echo.NewHTTPError(http.StatusInternalServerError, "Failed to retrieve API keys")
	}

	// Return empty list instead of null if no keys exist
	if apiKeys == nil {
		apiKeys = []db_gen.ApiKey{}
	}

	return c.JSON(http.StatusOK, apiKeys)
}

// HandleDeleteAPIKey handles deleting an API key by its key value.
func HandleDeleteAPIKey(c echo.Context) error {
	key := c.Param("key") // Assuming key is passed as a URL parameter e.g., /api/keys/:key
	if key == "" {
		return echo.NewHTTPError(http.StatusBadRequest, "API key parameter is required")
	}

	// Optional: Check if key exists before attempting delete to provide 404 if not found
	_, err := GetAPIKey(c.Request().Context(), key)
	if err != nil {
		if err == sql.ErrNoRows {
			return echo.NewHTTPError(http.StatusNotFound, "API key not found")
		}
		c.Logger().Error("Failed to check API key before delete:", err)
		return echo.NewHTTPError(http.StatusInternalServerError, "Failed to delete API key")
	}

	err = DeleteAPIKey(c.Request().Context(), key)
	if err != nil {
		c.Logger().Error("Failed to delete API key:", err)
		return echo.NewHTTPError(http.StatusInternalServerError, "Failed to delete API key")
	}

	return c.NoContent(http.StatusNoContent)
}
