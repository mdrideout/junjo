# File: backend/Makefile

# --- Configuration ---
# Define variables for paths to make the script easy to configure.
# DB_NAME is the local database file used for development.
DB_NAME ?= dev.db
DB_DIR  ?= db
MIGRATIONS_DIR = $(DB_DIR)/migrations
SCHEMA_FILE    = $(DB_DIR)/schema.sql

# --- Commands ---
# .PHONY tells Make that these are not files to be built.
.PHONY: help db-new-migration db-migrate-up db-regenerate proto

# A 'help' command is a good practice to explain how to use the Makefile.
help:
	@echo "Available commands:"
	@echo "  make db-new-migration name=<migration_name>  --- Creates a new SQL migration file."
	@echo "  make db-migrate-up                           --- Applies all pending migrations to a temporary database."
	@echo "  make db-regenerate                           --- The main workflow: migrates, dumps schema, and generates sqlc code."
	@echo "                                                   This ensures Go code is in sync with database migrations."
	@echo "  make proto                                   --- Generates protobuf Go code from .proto files."
	@echo "  make sqlc-generate                           --- Generates sqlc code from current schema."

# This command creates a new, timestamped migration file using the Goose CLI.
# It requires a 'name' argument, like: make db-new-migration name=add_tags_to_posts
db-new-migration:
	@if [ -z "$(name)" ]; then \
		echo "Usage: make db-new-migration name=<migration_name>"; \
		exit 1; \
	fi
	@echo ">> Creating new migration: $(name)"
	@goose -dir $(MIGRATIONS_DIR) create $(name) sql

# This command simply runs all 'up' migrations against the development database.
db-migrate-up:
	@echo ">> Applying database migrations to in-memory database..."
	@goose -dir $(MIGRATIONS_DIR) sqlite3 ":memory:" up

# This is the primary workflow command. It automates the three key steps
# required after creating and editing a new migration file.
db-regenerate:
	@echo ">> Applying database migrations to temporary database and dumping schema..."
	@rm -f temp.db
	@goose -dir $(MIGRATIONS_DIR) sqlite3 "temp.db" up
	@sqlite3 "temp.db" .schema > $(SCHEMA_FILE)
	@rm -f temp.db
	@echo ">> Generating sqlc code..."
	@sqlc generate
	@echo "✅ Workflow complete! Go code is now in sync with the new schema."

# Proto generation target
proto:
	protoc \
	--go_out=./proto_gen \
	--go-grpc_out=./proto_gen \
	./proto/*.proto

sqlc-generate:
	@echo ">> Generating sqlc code..."
	@sqlc generate