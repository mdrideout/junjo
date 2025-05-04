package auth

import (
	"errors"
	"log"
	"net/http"
	"strconv"

	"junjo-server/db_gen"

	"github.com/gorilla/sessions"
	"github.com/labstack/echo-contrib/session"
	"github.com/labstack/echo/v4"
	"golang.org/x/crypto/bcrypt"
	"modernc.org/sqlite"
)

// HandleDbHasUsers calls the repository to check user existence.
func HandleDbHasUsers(c echo.Context) error {
	c.Logger().Printf("Running UsersExist function")

	exists, err := DbHasUsers(c.Request().Context())
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{
			"error": "Failed to fetch user existence",
		})
	}

	return c.JSON(http.StatusOK, map[string]bool{
		"usersExist": exists,
	})
}

// HandleCreateFirstUser calls the repository to create the first user.
func HandleCreateFirstUser(c echo.Context) error {
	c.Logger().Printf("Running HandleCreateFirstUser function")

	var req CreateUserRequest
	if err := c.Bind(&req); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, err.Error())
	}

	// Check if any users exist
	exists, err := DbHasUsers(c.Request().Context())
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{
			"error": "Failed check authorization for first user creation.",
		})
	}
	if exists {
		return c.JSON(http.StatusBadRequest, map[string]string{
			"error": "Users already exist, cannot create first user.",
		})
	}

	// Hash the provided password
	hashedPassword, err := hashPassword(req.Password)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{
			"error": "Failed to hash password",
		})
	}

	// Create the first user
	create_err := CreateUser(c.Request().Context(), req.Email, hashedPassword)
	if create_err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{
			"error": "Failed to create first user",
		})
	}

	return c.JSON(http.StatusOK, map[string]string{
		"message": "First user created successfully",
	})
}

func HandleCreateUser(c echo.Context) error {
	var req CreateUserRequest
	if err := c.Bind(&req); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, err.Error())
	}

	// Hash the provided password
	hashedPassword, err := hashPassword(req.Password)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{
			"error": "Failed to hash password",
		})
	}

	err = CreateUser(c.Request().Context(), req.Email, hashedPassword)
	if err != nil {
		var sqliteErr *sqlite.Error

		if errors.As(err, &sqliteErr) {
			// Check if the extended error code is 2067 (SQLITE_CONSTRAINT_UNIQUE)
			if sqliteErr.Code() == 2067 {
				return c.JSON(http.StatusConflict, map[string]string{
					"error": "A user with this email already exists",
				})
			}
		}

		// Other errors
		c.Logger().Errorf("Database error during user creation: %v (Code: %d)", err, sqliteErr.Code())
		return c.JSON(http.StatusInternalServerError, map[string]string{
			"error": "Failed to create user due to a database error",
		})
	}

	return c.JSON(http.StatusOK, map[string]string{
		"message": "User created successfully",
	})
}

func HandleListUsers(c echo.Context) error {
	users, err := ListUsers(c.Request().Context())
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{
			"error": "Failed to fetch users",
		})
	}

	// Return empty list instead of null if no users exist
	if users == nil {
		users = []db_gen.ListUsersRow{}
	}

	return c.JSON(http.StatusOK, users)
}

func HandleDeleteUser(c echo.Context) error {
	id := c.Param("id")
	if id == "" {
		return echo.NewHTTPError(http.StatusBadRequest, "User ID is required")
	}

	// Convert id to int64
	userID, err := strconv.ParseInt(id, 10, 64)
	if err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, "Invalid user ID format")
	}

	err = DeleteUser(c.Request().Context(), userID)
	if err != nil {
		return echo.NewHTTPError(http.StatusInternalServerError, "Failed to delete user")
	}

	return c.JSON(http.StatusOK, map[string]string{
		"message": "User deleted successfully",
	})
}

func SignIn(c echo.Context) error {
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
	user, err := ValidateCredentials(c, req.Email, req.Password)
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

func hashPassword(password string) (string, error) {
	// Hash the password using bcrypt
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", err
	}

	// Convert the hashed password to a string
	return string(hashedPassword), nil
}

func ComparePasswords(hashedPassword, plainPassword string) error {
	return bcrypt.CompareHashAndPassword([]byte(hashedPassword), []byte(plainPassword))
}

func ValidateCredentials(c echo.Context, email, password string) (*db_gen.User, error) {
	// Fetch the user from the database
	user, err := GetUserByEmail(c.Request().Context(), email)
	if err != nil {
		return nil, err
	}

	// Compare the provided password with the hashed password
	if err := ComparePasswords(user.PasswordHash, password); err == nil {
		return &user, nil
	}

	return nil, errors.New("invalid credentials")
}
