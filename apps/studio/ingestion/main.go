package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"junjo-ai-studio/ingestion/backend_client"
	"junjo-ai-studio/ingestion/config"
	"junjo-ai-studio/ingestion/logger"
	"junjo-ai-studio/ingestion/server"
	"junjo-ai-studio/ingestion/storage"
)

func main() {
	// Load configuration and initialize logger
	config.MustLoad()
	logger.Init()

	slog.Info("starting ingestion service")

	cfg := config.Get()

	// Ensure the database directory exists (0700 = owner-only access)
	dbDir := filepath.Dir(cfg.SQLite.Path)
	if err := os.MkdirAll(dbDir, 0700); err != nil {
		slog.Error("failed to create database directory", slog.String("path", dbDir), slog.Any("error", err))
		os.Exit(1)
	}

	// Create repository
	slog.Info("initializing sqlite", slog.String("path", cfg.SQLite.Path))
	repo, err := storage.NewSQLiteRepository(cfg.SQLite.Path)
	if err != nil {
		slog.Error("failed to create repository", slog.Any("error", err))
		os.Exit(1)
	}

	slog.Info("storage initialized successfully")

	// Create backend auth client
	authClient, err := backend_client.NewAuthClient()
	if err != nil {
		slog.Error("failed to create backend auth client", slog.Any("error", err))
		os.Exit(1)
	}
	defer authClient.Close()

	// Wait for the backend to be ready before accepting any traffic
	slog.Info("waiting for backend to be ready")
	if err := authClient.WaitUntilReady(context.Background()); err != nil {
		slog.Error("backend connection failed", slog.Any("error", err))
		os.Exit(1)
	}

	// Create flusher with backend notification callback
	flusher := storage.NewFlusher(repo)
	flusher.SetNotifyFunc(func(ctx context.Context, filePath string) error {
		_, err := authClient.NotifyNewParquetFile(ctx, filePath)
		return err
	})
	flusher.Start()

	// Create batched span logger (logs every 10 seconds instead of per-span)
	spanLogger := server.NewBatchedSpanLogger(10 * time.Second)
	spanLogger.Start()

	// Create the public gRPC server
	publicGRPCServer, publicLis, err := server.NewGRPCServer(repo, authClient, spanLogger)
	if err != nil {
		slog.Error("failed to create public grpc server", slog.Any("error", err))
		os.Exit(1)
	}

	go func() {
		slog.Info("public grpc server listening", slog.String("address", publicLis.Addr().String()))
		if err := publicGRPCServer.Serve(publicLis); err != nil {
			slog.Error("failed to serve public grpc", slog.Any("error", err))
			os.Exit(1)
		}
	}()

	// Create the internal gRPC server
	internalGRPCServer, internalLis, err := server.NewInternalGRPCServer(repo, flusher)
	if err != nil {
		slog.Error("failed to create internal grpc server", slog.Any("error", err))
		os.Exit(1)
	}

	go func() {
		slog.Info("internal grpc server listening", slog.String("address", internalLis.Addr().String()))
		if err := internalGRPCServer.Serve(internalLis); err != nil {
			slog.Error("failed to serve internal grpc", slog.Any("error", err))
			os.Exit(1)
		}
	}()

	// Graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	slog.Info("shutting down grpc servers")
	publicGRPCServer.GracefulStop()
	internalGRPCServer.GracefulStop()
	slog.Info("grpc servers stopped")

	// Stop span logger (flushes any remaining log entries)
	spanLogger.Stop()

	// Stop flusher (performs final flush before stopping)
	flusher.Stop()

	slog.Info("syncing database to disk")
	if err := repo.Sync(); err != nil {
		slog.Warn("failed to sync database", slog.Any("error", err))
	} else {
		slog.Info("database sync completed")
	}

	slog.Info("closing database")
	if err := repo.Close(); err != nil {
		slog.Error("failed to close database", slog.Any("error", err))
		os.Exit(1)
	}
	slog.Info("database closed successfully")
}
