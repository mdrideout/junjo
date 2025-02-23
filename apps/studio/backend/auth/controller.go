package auth

import (
	"net/http"

	"github.com/labstack/echo/v4"
)

func InitRoutes(e *echo.Echo) {
	e.POST("/sign-in", SignIn)
	e.POST("/sign-out", SignOut)
	e.POST("/hash-password", HashPassword)
	e.GET("/auth-test", AuthTest)

	// Can be called immediately after sign in to get a CSRF token
	e.GET("/csrf", func(c echo.Context) error {
		return c.JSON(http.StatusOK, map[string]string{"csrfToken": c.Get("csrf").(string)})
	})
}
