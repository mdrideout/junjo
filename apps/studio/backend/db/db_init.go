// File: db_init.go

package db

import (
	"context"
	"database/sql"
	"embed" // Import the 'embed' package to include migration files in the binary
	"fmt"
	"log"

	"github.com/pressly/goose/v3" // Import the Goose library
	_ "modernc.org/sqlite"
)

// The //go:embed directive tells the Go compiler to embed the contents of the
// 'migrations' directory into the 'embedMigrations' variable.
//
//go:embed migrations/*.sql
var embedMigrations embed.FS

// Global database connection variable.
var DB *sql.DB

// Connect initializes the database connection and runs all pending migrations.
func Connect() {
	ctx := context.Background()
	dbPath := "/dbdata/sqlite/app_data.db"

	// Open the database connection using the sqlite driver.
	var err error
	DB, err = sql.Open("sqlite", dbPath)
	if err != nil {
		log.Fatalf("Failed to open database: %v", err)
	}

	if err = DB.Ping(); err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	fmt.Println("Successfully connected to the SQLite database!")

	// --- Goose Migration Logic ---
	// Tell Goose to use the embedded files as the source for migrations.
	goose.SetBaseFS(embedMigrations)

	// Set the database dialect for Goose.
	if err := goose.SetDialect("sqlite"); err != nil {
		log.Fatalf("Failed to set goose dialect: %v", err)
	}

	// Run all 'up' migrations. Goose keeps track of which migrations have
	// already been applied and only runs the new ones.
	if err := goose.Up(DB, "migrations"); err != nil {
		log.Fatalf("Failed to run goose migrations: %v", err)
	}
	log.Println("Database migrations applied successfully!")

	// --- Performance & Safety PRAGMAs ---
	_, err = DB.ExecContext(ctx, "PRAGMA journal_mode=WAL")
	if err != nil {
		log.Fatalf("Failed to set WAL mode: %v", err)
	}
	_, err = DB.ExecContext(ctx, "PRAGMA synchronous = NORMAL")
	if err != nil {
		log.Fatalf("Failed to set synchronous mode: %v", err)
	}
}

// Close safely closes the database connection.
func Close() {
	if DB != nil {
		DB.Close()
	}
}
