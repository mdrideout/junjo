package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	"junjo-ai-studio/ingestion/backend_client"
	"junjo-ai-studio/ingestion/logger"
	"junjo-ai-studio/ingestion/server"
	"junjo-ai-studio/ingestion/storage"
)

func main() {
	// Initialize logger
	log := logger.InitLogger()
	log.Info("starting ingestion service")

	// --- BadgerDB Setup ---
	dbPath := os.Getenv("JUNJO_BADGERDB_PATH")
	if dbPath == "" {
		// Default to a local directory for development
		homeDir, err := os.UserHomeDir()
		if err != nil {
			log.Error("failed to get user home directory", slog.Any("error", err))
			os.Exit(1)
		}
		dbPath = filepath.Join(homeDir, ".junjo", "ingestion-wal")
	}

	// Ensure the directory exists (0700 = owner-only access)
	if err := os.MkdirAll(dbPath, 0700); err != nil {
		log.Error("failed to create database directory", slog.String("path", dbPath), slog.Any("error", err))
		os.Exit(1)
	}

	log.Info("initializing badgerdb", slog.String("path", dbPath))
	store, err := storage.NewStorage(dbPath)
	if err != nil {
		log.Error("failed to initialize storage", slog.Any("error", err))
		os.Exit(1)
	}
	// We will call Close() explicitly in the shutdown block.

	log.Info("storage initialized successfully")

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
