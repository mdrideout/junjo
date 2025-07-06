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

	// Middleware
	e.Pre(middleware.Recover()) // Recover must be first
	e.Use(middleware.Logger())

	// CORS middleware
	// Must be registered with `Pre` to run before the router, which allows it to handle
	// OPTIONS requests for routes that don't have an explicit OPTIONS handler.
	allowedOriginsEnv := os.Getenv("JUNJO_ALLOW_ORIGINS")
	config := middleware.CORSConfig{
		AllowMethods:     []string{http.MethodGet, http.MethodPost, http.MethodPut, http.MethodDelete, http.MethodOptions},
		AllowHeaders:     []string{echo.HeaderOrigin, echo.HeaderContentType, echo.HeaderAccept, echo.HeaderXCSRFToken},
		AllowCredentials: true,
	}

	// AllowOriginFunc is a custom function to validate the origin.
	// It's used here to provide more robust logging and explicit control over the CORS logic.
	// According to Echo docs, if this option is set, the AllowOrigins array is ignored.
	config.AllowOriginFunc = func(origin string) (bool, error) {
		allowedOriginsEnv := os.Getenv("JUNJO_ALLOW_ORIGINS")
		if len(allowedOriginsEnv) == 0 {
			e.Logger.Infof("CORS check: JUNJO_ALLOW_ORIGINS not set. Allowing origin for local dev: %s", origin)
			return true, nil
		}

		allowedOrigins := strings.Split(allowedOriginsEnv, ",")
		for _, allowed := range allowedOrigins {
			trimmedAllowed := strings.TrimSpace(allowed)
			if trimmedAllowed == origin {
				e.Logger.Infof("CORS check: Allowing origin (exact match): %s", origin)
				return true, nil
			}
		}

		e.Logger.Warnf("CORS check: Denying origin: %s. Not in JUNJO_ALLOW_ORIGINS.", origin)
		return false, nil
	}

	// Log the configured origins for clarity on startup
	if len(allowedOriginsEnv) > 0 {
		e.Logger.Printf("CORS Allowed Origins configured via JUNJO_ALLOW_ORIGINS: %s", allowedOriginsEnv)
	} else {
		e.Logger.Printf("CORS Allowed Origins not set. Reflecting any origin.")
	}
	e.Pre(middleware.CORSWithConfig(config))

	// Session Middleware
	sessionSecret := os.Getenv("JUNJO_SESSION_SECRET")
	if sessionSecret == "" {
		log.Fatal("JUNJO_SESSION_SECRET environment variable is not set")
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
