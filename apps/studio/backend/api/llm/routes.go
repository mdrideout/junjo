package llm

import (
	"github.com/labstack/echo/v4"
)

// RegisterRoutes registers the LLM service routes.
func RegisterRoutes(e *echo.Echo) {
	e.POST("/llm/generate", HandleGeminiTextRequest)
}
