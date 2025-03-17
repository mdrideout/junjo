package db_duckdb

import (
	"context"
	"database/sql"
	_ "embed"
	"fmt"
	"log"

	_ "github.com/marcboeker/go-duckdb" // Import the DuckDB driver
)

//go:embed test_schema.sql
var testSchema string

// DB is a global variable to hold the database connection.
var DB *sql.DB

// Connect initializes the database connection.
func Connect() error {
	ctx := context.Background()
	fmt.Println("Connecting to duckdb...")
	dbPath := "/data/duckdb/telemetry.db"
	var err error

	// Open the database connection.
	DB, err = sql.Open("duckdb", dbPath)
	if err != nil {
		return fmt.Errorf("failed to open duckdb database: %w", err)
	}
	fmt.Println("Opened duckdb.")

	// Ping the database to verify the connection.
	if err := DB.Ping(); err != nil {
		return fmt.Errorf("failed to ping duckdb database: %w", err)
	}
	fmt.Println("Pinged duckdb.")

	//Initialize Tables
	if err := initializeTables(ctx); err != nil {
		log.Fatalf("Failed to initialize tables: %v", err)
	}

	fmt.Println("duckdb connection established successfully.")
	return nil
}

func initializeTables(ctx context.Context) error {
	// Check if table exists.  DuckDB's information_schema is reliable.
	var exists bool
	//Check for the people table
	err := DB.QueryRowContext(ctx, "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'people')").Scan(&exists)
	if err != nil {
		return fmt.Errorf("failed to check if table 'people' exists: %w", err)
	}

	if !exists {
		// Create table and insert if !exists
		// use testSchema here
		if _, err := DB.ExecContext(ctx, testSchema); err != nil {
			return fmt.Errorf("failed to execute schema: %w", err)
		}
		fmt.Println("people table created and populated")
	}
	return nil
}

// CloseDB closes the database connection.
func Close() {
	if DB != nil {
		if err := DB.Close(); err != nil {
			fmt.Printf("Error closing duckdb database: %v", err)
		}
	}
}
