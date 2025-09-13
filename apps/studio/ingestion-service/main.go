package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

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

	// --- gRPC Server Setup ---
	grpcServer, lis, err := server.NewGRPCServer(store)
	if err != nil {
		log.Fatalf("Failed to create gRPC server: %v", err)
	}

	// Start the server in a goroutine so it doesn't block.
	go func() {
		log.Printf("gRPC server listening at %v", lis.Addr())
		if err := grpcServer.Serve(lis); err != nil {
			log.Fatalf("Failed to serve gRPC: %v", err)
		}
	}()

	// --- Graceful Shutdown ---
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit // Block until a signal is received.

	log.Println("Shutting down gRPC server...")
	grpcServer.GracefulStop()
	log.Println("gRPC server stopped.")

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
