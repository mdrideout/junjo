package db

import (
	"context"
	"database/sql"
	_ "embed"
	"fmt"
	"log"

	_ "modernc.org/sqlite"
)

// embed the schema.sql file (ddl = data definition language)
//
//go:embed schema.sql
var ddl string

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

	// Check if the table already exists
	var tableName string
	err = DB.QueryRowContext(ctx, "SELECT name FROM sqlite_master WHERE type='table' AND name='workflow_logs';").Scan(&tableName)
	if err != nil && err != sql.ErrNoRows {
		log.Fatalf("Failed to check if table exists: %v", err)
	}

	// Create tables with the embedded schema if they do not exist
	if tableName == "" {
		if _, err := DB.ExecContext(ctx, ddl); err != nil {
			log.Fatalf("Failed to execute schema: %v", err)
		}
	}
}

// Close closes the database connection
func Close() {
	if DB != nil {
		DB.Close()
	}
}
