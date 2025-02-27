package db

import (
	"context"
	"database/sql"
	_ "embed"
	"fmt"
	"log"

	_ "modernc.org/sqlite"
)

// embed the schema files
//
//go:embed workflow_logs/schema.sql
var workflowLogsSchema string

//go:embed workflow_metadata/schema.sql
var workflowMetadataSchema string

var DB *sql.DB

// Connect initializes the database connection
func Connect() {
	ctx := context.Background()
	dbPath := "/data/sqlite/telemetry.db"

	// Open the database connection
	var err error
	DB, err = sql.Open("sqlite", dbPath)
	if err != nil {
		log.Fatalf("Failed to open database: %v", err)
	}

	// Verify the connection
	err = DB.Ping()
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}

	fmt.Println("Successfully connected to the SQLite database!")

	// Enable WAL (Write-Ahead Logging) mode for better concurrency and performance.
	// WAL provides better concurrency and crash recovery.
	_, err = DB.ExecContext(ctx, "PRAGMA journal_mode=WAL")
	if err != nil {
		log.Fatalf("Failed to set WAL mode: %v", err)
	}

	// Set synchronous to NORMAL. This improves performance by reducing the fsync calls.
	// It offers a balance between speed and data safety.  In NORMAL mode, fsync operations
	// happen less frequently.
	_, err = DB.ExecContext(ctx, "PRAGMA synchronous = NORMAL")
	if err != nil {
		log.Fatalf("Failed to set synchronous mode: %v", err)
	}

	// Initialize tables
	if err := initializeTables(ctx); err != nil {
		log.Fatalf("Failed to initialize tables: %v", err)
	}
}

// initializeTables creates tables if they don't exist
func initializeTables(ctx context.Context) error {
	tables := map[string]string{
		"workflow_logs":     workflowLogsSchema,
		"workflow_metadata": workflowMetadataSchema,
	}

	for tableName, schema := range tables {
		// Check if table exists
		var exists string
		err := DB.QueryRowContext(ctx,
			"SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
			tableName).Scan(&exists)

		if err != nil && err != sql.ErrNoRows {
			return fmt.Errorf("failed to check if table %s exists: %v", tableName, err)
		}

		// Create table if it doesn't exist
		if exists == "" {
			if _, err := DB.ExecContext(ctx, schema); err != nil {
				return fmt.Errorf("failed to create table %s: %v", tableName, err)
			}
			fmt.Printf("Created table: %s\n", tableName)
		}
	}
	return nil
}

// Close closes the database connection
func Close() {
	if DB != nil {
		DB.Close()
	}
}
