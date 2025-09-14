package otel_token

import "github.com/labstack/echo/v4"

// InitRoutes initializes the routes for the OTel token endpoint.
func InitRoutes(e *echo.Echo) {
	g := e.Group("/api/v1/otel")
	g.POST("/token", HandleOTelTokenRequest)
}
