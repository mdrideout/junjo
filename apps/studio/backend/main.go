package main

import (
	"database/sql"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"

	"context"
	"junjo-server/api"
	"junjo-server/api_keys"
	"junjo-server/auth"
	"junjo-server/db"
	"junjo-server/db_duckdb"
	"junjo-server/db_gen"
	"junjo-server/ingestion_client"
	m "junjo-server/middleware"
	"junjo-server/telemetry"
	u "junjo-server/utils"
	"time"

	"github.com/gorilla/sessions"
	"github.com/joho/godotenv"
	"github.com/labstack/echo-contrib/session"
	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/proto"
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

	// Ingestion Client
	ingestionClient, err := ingestion_client.NewClient()
	if err != nil {
		log.Fatalf("Failed to create ingestion client: %v", err)
	}
	defer ingestionClient.Close()

	// Start a background goroutine to poll for spans
	go func() {
		ticker := time.NewTicker(3 * time.Second) // Poll every 3 seconds
		defer ticker.Stop()

		queries := db_gen.New(db.DB)
		var lastKey []byte
		// At startup, try to load the last processed key from the database.
		retrievedKey, err := queries.GetPollerState(context.Background())
		if err != nil && err != sql.ErrNoRows {
			log.Fatalf("Failed to load poller state: %v", err)
		} else if err == sql.ErrNoRows {
			log.Println("No previous poller state found. Starting from the beginning.")
		} else {
			lastKey = retrievedKey
			log.Printf("Resuming poller from last key: %x", lastKey)
		}

		for range ticker.C {
			log.Println("Polling for new spans...")
			spans, err := ingestionClient.ReadSpans(context.Background(), lastKey, 100)
			if err != nil {
				log.Printf("Error reading spans: %v", err)
				continue
			}

			if len(spans) > 0 {
				lastKey = spans[len(spans)-1].KeyUlid
				log.Printf("Received %d spans. Last key: %x", len(spans), lastKey)
				var processedSpans []*tracepb.Span
				for _, receivedSpan := range spans {
					var span tracepb.Span
					if err := proto.Unmarshal(receivedSpan.SpanBytes, &span); err != nil {
						log.Printf("Error unmarshaling span: %v", err)
						continue // Skip to the next span
					}
					processedSpans = append(processedSpans, &span)
				}

				if len(processedSpans) > 0 {
					// TODO: The service name should be retrieved from the resource spans,
					// but the current ingestion service only provides the span.
					// This needs to be addressed in the ingestion service.
					serviceName := "NO_SERVICE_NAME"
					if err := telemetry.BatchProcessSpans(context.Background(), serviceName, processedSpans); err != nil {
						log.Printf("Error processing spans batch: %v", err)
					} else {
						// If the batch was processed successfully, update the last key in the database.
						err := queries.UpsertPollerState(context.Background(), lastKey)
						if err != nil {
							log.Printf("Failed to save poller state: %v", err)
						}
					}
				}
			} else {
				log.Println("No new spans found.")
			}
		}
	}()

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
