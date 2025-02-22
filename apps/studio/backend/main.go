package main

import (
	"fmt"
	"log"
	"net/http"
	"os"

	"junjo-ui-backend/auth"
	m "junjo-ui-backend/middleware"
	u "junjo-ui-backend/utils"

	"github.com/joho/godotenv"
	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"
)

func main() {
	fmt.Println("Running main.go function")

	// Load environment variables
	err := godotenv.Load(".env")
	if err != nil {
		log.Println(".env file could not be loaded")
	}
	env := os.Getenv("ENV")
	fmt.Println("Environment: ", env)

	// Host
	port := "1323"
	host := "0.0.0.0"
	serverHostPort := host + ":" + port

	// // Database
	// db.Connect()

	// Initialize Echo
	e := echo.New()
	e.Logger.Printf("initialized echo with host:port %s", serverHostPort)
	e.Validator = u.NewCustomValidator()

	// Other Middleware
	e.Use(middleware.Logger())
	e.Use(middleware.Recover())

	// CORS middleware
	e.Use(middleware.CORSWithConfig(middleware.CORSConfig{
		AllowOrigins: []string{"http://localhost:5173"}, // Update this to your frontend's URL
		AllowMethods: []string{echo.GET, echo.POST, echo.PUT, echo.DELETE},
	}))

	// Auth Middleware
	e.Use(m.Auth()) // Auth guard all routes

	// ROUTES
	auth.InitRoutes(e)

	e.GET("/ping", func(c echo.Context) error {
		return c.String(http.StatusOK, "pong")
	})

	// Start the server
	e.Logger.Fatal(e.Start(serverHostPort))
}
