package auth

import (
	"net/http"

	"github.com/labstack/echo-contrib/session"
	"github.com/labstack/echo/v4"
)

func GetUserEmailFromSession(c echo.Context) (string, error) {
	sess, err := session.Get("session", c)
	if err != nil {
		return "", err // Session error (e.g., invalid cookie)
	}

	userEmail, ok := sess.Values["userEmail"].(string)
	if !ok {
		return "", http.ErrNoCookie // No userEmail in session (not logged in)
	}
	return userEmail, nil
}
