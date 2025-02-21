package auth

import (
	"log"
	"net/http"

	"github.com/labstack/echo/v4"
	"golang.org/x/crypto/bcrypt"
)

func SignIn(c echo.Context) error {
	type SigninRequest struct {
		Email    string `json:"email" validate:"required,email"`
		Password string `json:"password" validate:"required"`
	}

	var req SigninRequest
	if err := c.Bind(&req); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, err.Error())
	}

	if err := c.Validate(&req); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, err.Error())
	}

	// Log the credentials
	c.Logger().Printf("Email: %s, Password: %s", req.Email, req.Password)

	// TODO: Implement proper user authentication against database
	// This is just an example
	if req.Email == "boon4376@gmail.com" && req.Password == "password" {
		token, err := GenerateJWT(req.Email)
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

func AuthTest(c echo.Context) error {
	user := c.Get("user").(*JWTCustomClaims)
	return c.JSON(http.StatusOK, user)
}

func HashPassword(c echo.Context) error {
	type PasswordRequest struct {
		Password string `json:"password" validate:"required"`
	}

	var req PasswordRequest
	if err := c.Bind(&req); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, err.Error())
	}

	if err := c.Validate(&req); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, err.Error())
	}

	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to hash password")
	}

	return c.JSON(http.StatusOK, map[string]string{
		"hashedPassword": string(hashedPassword),
	})
}
