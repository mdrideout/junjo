package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	"junjo-ai-studio/ingestion/backend_client"
	"junjo-ai-studio/ingestion/logger"
	"junjo-ai-studio/ingestion/server"
	"junjo-ai-studio/ingestion/storage"
)

func main() {
	// Initialize logger
	log := logger.InitLogger()
	log.Info("starting ingestion service")

	// --- SQLite WAL Setup ---
	dbPath := os.Getenv("JUNJO_WAL_SQLITE_PATH")
	if dbPath == "" {
		// Default to a local directory for development
		homeDir, err := os.UserHomeDir()
		if err != nil {
			log.Error("failed to get user home directory", slog.Any("error", err))
			os.Exit(1)
		}
		dbPath = filepath.Join(homeDir, ".junjo", "ingestion-wal", "spans.db")
	}

	// Ensure the directory exists (0700 = owner-only access)
	dbDir := filepath.Dir(dbPath)
	if err := os.MkdirAll(dbDir, 0700); err != nil {
		log.Error("failed to create database directory", slog.String("path", dbDir), slog.Any("error", err))
		os.Exit(1)
	}

	log.Info("initializing sqlite", slog.String("path", dbPath))
	store, err := storage.NewStorage(dbPath)
	if err != nil {
		log.Error("failed to initialize storage", slog.Any("error", err))
		os.Exit(1)
	}
	// We will call Close() explicitly in the shutdown block.

	log.Info("storage initialized successfully")

	// --- Flusher Setup ---
	flusher := initFlusher(store, log)
	flusher.Start()

	// --- Dependency Injection Setup ---
	// The main function acts as the injector, creating and wiring together the
	// components of the application.

	// 1. Create the AuthClient: This client is responsible for communicating with
	//    the backend's internal authentication service.
	authClient, err := backend_client.NewAuthClient()
	if err != nil {
		log.Error("failed to create backend auth client", slog.Any("error", err))
		os.Exit(1)
	}
	defer authClient.Close()

	// 2. Wait for the backend to be ready before accepting any traffic.
	//    This ensures that API key validation will work from the very first request,
	//    preventing the startup race condition where the ingestion service starts
	//    before the backend's gRPC server is ready.
	//    We wait indefinitely since the ingestion service cannot function without the backend.
	log.Info("waiting for backend to be ready")
	if err := authClient.WaitUntilReady(context.Background()); err != nil {
		log.Error("backend connection failed", slog.Any("error", err))
		os.Exit(1)
	}

	// 3. Create the Public gRPC Server: This server handles all incoming public
	//    requests. It is injected with the components it depends on, such as the
	//    storage layer and the AuthClient.
	publicGRPCServer, publicLis, err := server.NewGRPCServer(store, authClient, log)
	if err != nil {
		log.Error("failed to create public grpc server", slog.Any("error", err))
		os.Exit(1)
	}

	go func() {
		log.Info("public grpc server listening", slog.String("address", publicLis.Addr().String()))
		if err := publicGRPCServer.Serve(publicLis); err != nil {
			log.Error("failed to serve public grpc", slog.Any("error", err))
			os.Exit(1)
		}
	}()

	// --- Internal gRPC Server Setup ---
	internalGRPCServer, internalLis, err := server.NewInternalGRPCServer(store, log)
	if err != nil {
		log.Error("failed to create internal grpc server", slog.Any("error", err))
		os.Exit(1)
	}

	go func() {
		log.Info("internal grpc server listening", slog.String("address", internalLis.Addr().String()))
		if err := internalGRPCServer.Serve(internalLis); err != nil {
			log.Error("failed to serve internal grpc", slog.Any("error", err))
			os.Exit(1)
		}
	}()

	// --- Graceful Shutdown ---
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit // Block until a signal is received.

	log.Info("shutting down grpc servers")
	publicGRPCServer.GracefulStop()
	internalGRPCServer.GracefulStop()
	log.Info("grpc servers stopped")

	// Stop flusher (performs final flush before stopping)
	log.Info("stopping flusher")
	flusher.Stop()
	log.Info("flusher stopped")

	log.Info("syncing database to disk")
	if err := store.Sync(); err != nil {
		// Log this as a warning, but still attempt to close.
		log.Warn("failed to sync database", slog.Any("error", err))
	} else {
		log.Info("database sync completed")
	}

	log.Info("closing database")
	if err := store.Close(); err != nil {
		log.Error("failed to close database", slog.Any("error", err))
		os.Exit(1)
	}
	log.Info("database closed successfully")
}

// initFlusher creates a flusher with configuration from environment variables.
func initFlusher(store *storage.Storage, log *slog.Logger) *storage.Flusher {
	config := storage.DefaultFlusherConfig()

	// SPAN_STORAGE_PATH: Base directory for Parquet files
	if path := os.Getenv("SPAN_STORAGE_PATH"); path != "" {
		config.OutputDir = path
	} else {
		// Default to a local directory for development
		homeDir, _ := os.UserHomeDir()
		config.OutputDir = filepath.Join(homeDir, ".junjo", "spans")
	}

	// FLUSH_INTERVAL: How often to check for flush conditions (default: 30s)
	if interval := os.Getenv("FLUSH_INTERVAL"); interval != "" {
		if d, err := time.ParseDuration(interval); err == nil {
			config.FlushInterval = d
		} else {
			log.Warn("invalid FLUSH_INTERVAL, using default", slog.String("value", interval))
		}
	}

	// FLUSH_MAX_AGE: Max age before flushing (default: 1h)
	if maxAge := os.Getenv("FLUSH_MAX_AGE"); maxAge != "" {
		if d, err := time.ParseDuration(maxAge); err == nil {
			config.MaxFlushAge = d
		} else {
			log.Warn("invalid FLUSH_MAX_AGE, using default", slog.String("value", maxAge))
		}
	}

	// FLUSH_MAX_ROWS: Max rows before flushing (default: 100000)
	if maxRows := os.Getenv("FLUSH_MAX_ROWS"); maxRows != "" {
		if n, err := strconv.ParseInt(maxRows, 10, 64); err == nil {
			config.MaxRowCount = n
		} else {
			log.Warn("invalid FLUSH_MAX_ROWS, using default", slog.String("value", maxRows))
		}
	}

	// FLUSH_MIN_ROWS: Minimum rows required to flush (default: 1000)
	if minRows := os.Getenv("FLUSH_MIN_ROWS"); minRows != "" {
		if n, err := strconv.ParseInt(minRows, 10, 64); err == nil {
			config.MinRowCount = n
		} else {
			log.Warn("invalid FLUSH_MIN_ROWS, using default", slog.String("value", minRows))
		}
	}

	log.Info("flusher configured",
		slog.String("output_dir", config.OutputDir),
		slog.Duration("flush_interval", config.FlushInterval),
		slog.Duration("max_age", config.MaxFlushAge),
		slog.Int64("max_rows", config.MaxRowCount),
		slog.Int64("min_rows", config.MinRowCount))

	return storage.NewFlusher(store, config)
}
