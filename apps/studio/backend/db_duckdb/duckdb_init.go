package db_duckdb

import (
	"context"
	"database/sql"
	_ "embed"
	"fmt"
	"log"

	_ "github.com/marcboeker/go-duckdb" // Import the DuckDB driver
)

//go:embed otel_spans/spans_schema.sql
var spansSchema string

//go:embed otel_spans/state_patches_schema.sql
var statePatchesSchema string

// DB is a global variable to hold the database connection.
var DB *sql.DB

// Connect initializes the database connection.
func Connect() error {
	ctx := context.Background()
	fmt.Println("Connecting to duckdb...")
	dbPath := "/dbdata/duckdb/otel_data.db"
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

	// spans_schema.sql
	if err := initTable("spans", spansSchema); err != nil {
		return fmt.Errorf("failed to initialize spans table: %w", err)
	}

	// state_patches_schema.sql
	if err := initTable("state_patches", statePatchesSchema); err != nil {
		return fmt.Errorf("failed to initialize state_patches table: %w", err)
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

// Initialize a table if it does not exist
func initTable(tableName string, schema string) error {
	ctx := context.Background()

	// Check if the table exists
	var exists bool
	err := DB.QueryRowContext(ctx, "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)", tableName).Scan(&exists)
	if err != nil {
		return fmt.Errorf("failed to check if table '%s' exists: %w", tableName, err)
	}

	if !exists {
		// Create the table
		if _, err := DB.ExecContext(ctx, schema); err != nil {
			return fmt.Errorf("failed to create table '%s': %w", tableName, err)
		}
		fmt.Printf("Table '%s' created\n", tableName)
	}
	return nil
}
