package auth

import (
	"errors"
	"log"
	"net/http"

	"junjo-server/db_gen"

	"github.com/gorilla/sessions"
	"github.com/labstack/echo-contrib/session"
	"github.com/labstack/echo/v4"
	"golang.org/x/crypto/bcrypt"
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

func hashPassword(password string) (string, error) {
	// Hash the password using bcrypt
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", err
	}

	// Convert the hashed password to a string
	return string(hashedPassword), nil
}

// func LoadUsersJsonDb() ([]User, error) {
// 	// Get the current working directory
// 	cwd, err := os.Getwd()
// 	if err != nil {
// 		return nil, err
// 	}

// 	// Construct the relative path to the JSON file
// 	filePath := filepath.Join(cwd, "user_db", "users-db.json")

// 	file, err := os.Open(filePath)
// 	if err != nil {
// 		return nil, err
// 	}
// 	defer file.Close()

// 	bytes, err := io.ReadAll(file)
// 	if err != nil {
// 		return nil, err
// 	}

// 	var users []User
// 	if err := json.Unmarshal(bytes, &users); err != nil {
// 		return nil, err
// 	}

// 	for _, user := range users {
// 		if user.Email == "" || user.Password == "" {
// 			return nil, errors.New("users json db contains invalid data: ensure fields properly conform to the []User struct")
// 		}
// 	}

// 	return users, nil
// }

func ComparePasswords(hashedPassword, plainPassword string) error {
	return bcrypt.CompareHashAndPassword([]byte(hashedPassword), []byte(plainPassword))
}

func ValidateCredentials(email, password string) (*db_gen.User, error) {
	users := []db_gen.User{}

	for _, user := range users {
		if user.Email == email {
			if err := ComparePasswords(user.PasswordHash, password); err == nil {
				return &user, nil
			}
			break
		}
	}

	return nil, errors.New("invalid credentials")
}
