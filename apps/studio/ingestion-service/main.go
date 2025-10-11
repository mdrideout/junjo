package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	"junjo-server/ingestion-service/backend_client"
	"junjo-server/ingestion-service/server"
	"junjo-server/ingestion-service/storage"
)

func main() {
	fmt.Println("Starting ingestion service...")

	// --- BadgerDB Setup ---
	dbPath := os.Getenv("BADGERDB_PATH")
	if dbPath == "" {
		// Default to a local directory for development
		homeDir, err := os.UserHomeDir()
		if err != nil {
			log.Fatalf("Failed to get user home directory: %v", err)
		}
		dbPath = filepath.Join(homeDir, ".junjo", "ingestion-wal")
	}

	// Ensure the directory exists
	if err := os.MkdirAll(dbPath, 0755); err != nil {
		log.Fatalf("Failed to create database directory at %s: %v", dbPath, err)
	}

	log.Printf("Initializing BadgerDB at: %s", dbPath)
	store, err := storage.NewStorage(dbPath)
	if err != nil {
		log.Fatalf("Failed to initialize storage: %v", err)
	}
	// We will call Close() explicitly in the shutdown block.

	log.Println("Storage initialized successfully.")

	// --- Dependency Injection Setup ---
	// The main function acts as the injector, creating and wiring together the
	// components of the application.

	// 1. Create the AuthClient: This client is responsible for communicating with
	//    the backend's internal authentication service.
	authClient, err := backend_client.NewAuthClient()
	if err != nil {
		log.Fatalf("Failed to create backend auth client: %v", err)
	}
	defer authClient.Close()

	// 2. Wait for the backend to be ready before accepting any traffic.
	//    This ensures that API key validation will work from the very first request,
	//    preventing the startup race condition where the ingestion service starts
	//    before the backend's gRPC server is ready.
	//    We wait indefinitely since the ingestion service cannot function without the backend.
	log.Println("Waiting for backend to be ready (no timeout - will wait indefinitely)...")
	if err := authClient.WaitUntilReady(context.Background()); err != nil {
		log.Fatalf("Backend connection failed: %v", err)
	}

	// 3. Create the Public gRPC Server: This server handles all incoming public
	//    requests. It is injected with the components it depends on, such as the
	//    storage layer and the AuthClient.
	publicGRPCServer, publicLis, err := server.NewGRPCServer(store, authClient)
	if err != nil {
		log.Fatalf("Failed to create public gRPC server: %v", err)
	}

	go func() {
		log.Printf("Public gRPC server listening at %v", publicLis.Addr())
		if err := publicGRPCServer.Serve(publicLis); err != nil {
			log.Fatalf("Failed to serve public gRPC: %v", err)
		}
	}()

	// --- Internal gRPC Server Setup ---
	internalGRPCServer, internalLis, err := server.NewInternalGRPCServer(store)
	if err != nil {
		log.Fatalf("Failed to create internal gRPC server: %v", err)
	}

	go func() {
		log.Printf("Internal gRPC server listening at %v", internalLis.Addr())
		if err := internalGRPCServer.Serve(internalLis); err != nil {
			log.Fatalf("Failed to serve internal gRPC: %v", err)
		}
	}()

	// --- Graceful Shutdown ---
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit // Block until a signal is received.

	log.Println("Shutting down gRPC servers...")
	publicGRPCServer.GracefulStop()
	internalGRPCServer.GracefulStop()
	log.Println("gRPC servers stopped.")

	log.Println("Attempting to sync database to disk...")
	if err := store.Sync(); err != nil {
		// Log this as a warning, but still attempt to close.
		log.Printf("Warning: failed to sync database: %v", err)
	} else {
		log.Println("Database sync completed successfully.")
	}

	log.Println("Attempting to close database...")
	if err := store.Close(); err != nil {
		log.Fatalf("FATAL: Failed to close database: %v", err)
	}
	log.Println("Database closed successfully.")
}
