package auth

import (
	"github.com/labstack/echo/v4"
)

func InitRoutes(e *echo.Echo) {
	e.POST("/sign-in", SignIn)
	e.POST("/sign-out", SignOut)
}
