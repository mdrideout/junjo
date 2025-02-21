package auth

import (
	"log"
	"net/http"

	"github.com/labstack/echo/v4"
)

type LoginRequest struct {
	Email    string `json:"email" validate:"required,email"`
	Password string `json:"password" validate:"required"`
}

func SignIn(c echo.Context) error {
	var login LoginRequest
	if err := c.Bind(&login); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, err.Error())
	}

	if err := c.Validate(&login); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, err.Error())
	}

	// Log the credentials
	c.Logger().Printf("Email: %s, Password: %s", login.Email, login.Password)

	// TODO: Implement proper user authentication against database
	// This is just an example
	if login.Email == "boon4376@gmail.com" && login.Password == "password" {
		token, err := GenerateJWT(login.Email)
		if err != nil {
			log.Printf("failed to generate token: %v", err)
			return echo.NewHTTPError(http.StatusInternalServerError, "failed to generate token")
		}
		return c.JSON(http.StatusOK, map[string]string{
			"token": token,
		})
	}

	return echo.NewHTTPError(http.StatusUnauthorized, "invalid credentials")
}

func SignOut(c echo.Context) error {
	// For stateless JWT, sign out is handled on the client side by deleting the token
	return c.NoContent(http.StatusOK)
}
