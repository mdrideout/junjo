package auth

import (
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"

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

	// Validate user credentials
	user, err := ValidateCredentials(req.Email, req.Password)
	if err != nil {
		log.Printf("failed to validate credentials: %v", err)
		return echo.NewHTTPError(http.StatusUnauthorized, "invalid credentials")
	}

	// Generate JWT token
	token, err := GenerateJWT(user.Email)
	if err != nil {
		log.Printf("failed to generate token: %v", err)
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to generate token")
	}

	return c.JSON(http.StatusOK, map[string]string{
		"token": token,
	})
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

func LoadUsersJsonDb() ([]User, error) {
	// Get the current working directory
	cwd, err := os.Getwd()
	if err != nil {
		return nil, err
	}

	// Construct the relative path to the JSON file
	filePath := filepath.Join(cwd, "user_db", "users-db.json")

	file, err := os.Open(filePath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	bytes, err := io.ReadAll(file)
	if err != nil {
		return nil, err
	}

	var users []User
	if err := json.Unmarshal(bytes, &users); err != nil {
		return nil, err
	}

	for _, user := range users {
		if user.Email == "" || user.Password == "" {
			return nil, errors.New("users json db contains invalid data: ensure fields properly conform to the []User struct")
		}
	}

	return users, nil
}

func ComparePasswords(hashedPassword, plainPassword string) error {
	return bcrypt.CompareHashAndPassword([]byte(hashedPassword), []byte(plainPassword))
}

func ValidateCredentials(email, password string) (*User, error) {
	users, err := LoadUsersJsonDb()
	if err != nil {
		return nil, err
	}

	for _, user := range users {
		if user.Email == email {
			if err := ComparePasswords(user.Password, password); err == nil {
				return &user, nil
			}
			break
		}
	}

	return nil, errors.New("invalid credentials")
}
