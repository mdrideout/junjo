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

	// --- Public gRPC Server Setup ---
	publicGRPCServer, publicLis, err := server.NewGRPCServer(store)
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
