package api_keys

import (
	"github.com/labstack/echo/v4"
)

func InitRoutes(e *echo.Echo) {
	keysGroup := e.Group("/api_keys")

	keysGroup.POST("", HandleCreateAPIKey)
	keysGroup.GET("", HandleListAPIKeys)
	keysGroup.DELETE("/:key", HandleDeleteAPIKey)
}
