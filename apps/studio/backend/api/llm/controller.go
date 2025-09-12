package llm

import (
	"net/http"

	"github.com/labstack/echo/v4"
)

// HandleGeminiTextRequest is the handler for the /llm/generate endpoint.
func HandleGeminiTextRequest(c echo.Context) error {
	var req GeminiRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": err.Error()})
	}

	// Set a default model if not provided
	if req.Model == "" {
		req.Model = "gemini-2.5-flash"
	}

	service := NewGeminiService()
	resp, err := service.GenerateContent(req)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": err.Error()})
	}

	return c.JSONBlob(http.StatusOK, resp)
}
