package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"

	"junjo-server/api"
	"junjo-server/api_keys"
	"junjo-server/auth"
	"junjo-server/db"
	"junjo-server/db_duckdb"
	m "junjo-server/middleware"
	"junjo-server/telemetry"
	u "junjo-server/utils"

	"github.com/gorilla/sessions"
	"github.com/joho/godotenv"
	"github.com/labstack/echo-contrib/session"
	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"
)

func main() {
	fmt.Println("Running main.go function")

	// Load environment variables
	err := godotenv.Load()
	if err != nil {
		fmt.Printf("%v\n", err)
	}

	// Host
	port := "1323"
	host := "0.0.0.0"
	serverHostPort := host + ":" + port

	// SQLite DB
	db.Connect()
	defer db.Close()

	// DuckDB
	duck_err := db_duckdb.Connect()
	if duck_err != nil {
		log.Fatalf("duckdb err: %v", duck_err)
	}
	defer db_duckdb.Close()

	// Initialize Echo
	e := echo.New()
	e.Logger.Printf("initialized echo with host:port %s", serverHostPort)
	e.Validator = u.NewCustomValidator()

	// Other Middleware
	e.Use(middleware.Logger())
	e.Use(middleware.Recover())

	// CORS middleware
	// CORS middleware
	allowedOriginsEnv := os.Getenv("ALLOW_ORIGINS")
	config := middleware.CORSConfig{
		AllowMethods:     []string{http.MethodGet, http.MethodPost, http.MethodPut, http.MethodDelete, http.MethodOptions},
		AllowHeaders:     []string{echo.HeaderOrigin, echo.HeaderContentType, echo.HeaderAccept, echo.HeaderXCSRFToken},
		AllowCredentials: true,
	}

	if len(allowedOriginsEnv) > 0 {
		// Use a fixed list of origins if the env var is set
		config.AllowOrigins = strings.Split(allowedOriginsEnv, ",")
		e.Logger.Printf("CORS Allowed Origins set to: %v", config.AllowOrigins)
	} else {
		// If the env var is not set, allow any origin by reflecting the request's origin.
		// This is required when AllowCredentials is true, as wildcard '*' is not allowed by browsers.
		config.AllowOriginFunc = func(origin string) (bool, error) {
			return true, nil
		}
		e.Logger.Printf("CORS Allowed Origins not set. Reflecting any origin.")
	}

	e.Use(middleware.CORSWithConfig(config))

	// Session Middleware
	sessionSecret := os.Getenv("SESSION_SECRET")
	if sessionSecret == "" {
		log.Fatal("SESSION_SECRET environment variable is not set")
	}
	e.Use(session.Middleware(sessions.NewCookieStore([]byte(sessionSecret))))

	// CSRF Middleware (Echo's built-in CSRF)
	e.Use(middleware.CSRFWithConfig(middleware.CSRFConfig{
		TokenLookup:    "header:X-CSRF-Token,cookie:csrf", // Look in header AND cookie
		CookieName:     "csrf",
		CookieSecure:   true, // HTTPS in production
		CookieHTTPOnly: true,
		CookieSameSite: http.SameSiteStrictMode,
		ContextKey:     "csrf", // Key to access CSRF token in handlers
		Skipper: func(c echo.Context) bool {
			if c.Request().Method == http.MethodOptions || c.Path() == "/sign-in" {
				return true // Skip CSRF check for OPTIONS and /sign-in
			}
			return false
		},
	}))

	// --- gRPC Server Setup (Start in a Goroutine) ---
	grpcServer, lis, err := telemetry.NewGRPCServer(db.DB)
	if err != nil {
		log.Fatalf("failed to create gRPC server: %v", err)
	}

	go func() { // Start the gRPC server in a separate goroutine!
		log.Printf("gRPC server listening at %v", lis.Addr())
		if err := grpcServer.Serve(lis); err != nil {
			log.Fatalf("failed to serve gRPC: %v", err)
		}
	}()

	// Auth Middleware
	e.Use(m.Auth()) // Auth guard all routes by default

	// ROUTES
	auth.InitRoutes(e)
	api.InitRoutes(e)
	api_keys.InitRoutes(e)

	// Ping route
	e.GET("/ping", func(c echo.Context) error {
		return c.String(http.StatusOK, "pong")
	})

	// Start the server
	e.Logger.Fatal(e.Start(serverHostPort))
}
