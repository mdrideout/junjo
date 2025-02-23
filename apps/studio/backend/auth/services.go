package auth

import (
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"

	"github.com/gorilla/sessions"
	"github.com/labstack/echo-contrib/session"
	"github.com/labstack/echo/v4"
	"golang.org/x/crypto/bcrypt"
)

func SignIn(c echo.Context) error {
	type SigninRequest struct {
		Email    string `json:"email" validate:"required,email"`
		Password string `json:"password" validate:"required"`
	}

	// Log the request
	log.Printf("request: %v", c.Request())

	var req SigninRequest
	if err := c.Bind(&req); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, err.Error())
	}

	if err := c.Validate(&req); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, err.Error())
	}

	// Validate user credentials
	user, err := ValidateCredentials(req.Email, req.Password)
	if err != nil {
		log.Printf("failed to validate credentials: %v", err)
		return echo.NewHTTPError(http.StatusUnauthorized, "invalid credentials")
	}

	// Create the session
	sess, err := session.Get("session", c)
	if err != nil {
		log.Printf("failed to get session: %v", err)
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to get session")
	}

	sess.Options = &sessions.Options{
		MaxAge:   86400 * 7, // 7 days
		HttpOnly: true,
		Secure:   true, // HTTPS in production
		SameSite: http.SameSiteStrictMode,
	}
	sess.Values["userEmail"] = user.Email
	if err := sess.Save(c.Request(), c.Response()); err != nil {
		log.Printf("failed to save session: %v", err)
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to save session")
	}

	return c.JSON(http.StatusOK, map[string]string{
		"message": "signed in",
	})
}

func SignOut(c echo.Context) error {
	// Destroy the session
	sess, err := session.Get("session", c)
	if err != nil {
		log.Printf("failed to get session: %v", err)
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to get session")
	}

	sess.Options.MaxAge = -1
	if err := sess.Save(c.Request(), c.Response()); err != nil {
		log.Printf("failed to save session: %v", err)
		return echo.NewHTTPError(http.StatusInternalServerError, "failed to save session")
	}

	return c.JSON(http.StatusOK, map[string]string{
		"message": "signed out",
	})
}

func AuthTest(c echo.Context) error {
	userEmail, err := GetUserEmailFromSession(c)
	if err != nil {
		log.Printf("failed to get userEmail from session: %v", err)
		return echo.NewHTTPError(http.StatusUnauthorized, "unauthorized")
	}

	return c.JSON(http.StatusOK, map[string]string{
		"userEmail": userEmail,
	})
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
