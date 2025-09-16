# Plan: Implementing Database Migrations with Goose

This document outlines the steps to integrate `goose` into the `backend` service to provide a robust and automated database migration system.

## 1. Add Goose Dependency

We will add the `goose` library to the `backend`'s `go.mod` file by running the following command in the `backend` directory:
```bash
go get github.com/pressly/goose/v3
```

## 2. Create Migration Files

A new directory will be created at `backend/db/migrations`. The existing schemas will be converted into Goose-compatible SQL files. Each file will contain both the `up` and `down` migrations, separated by `-- +goose Down` comments.

- **`backend/db/migrations/00001_create_users_table.sql`**:
  ```sql
  -- +goose Up
  CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

  -- +goose Down
  DROP TABLE IF EXISTS users;
  ```

- **`backend/db/migrations/00002_create_api_keys_table.sql`**:
  ```sql
  -- +goose Up
  CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

  -- +goose Down
  DROP TABLE IF EXISTS api_keys;
  ```

- **`backend/db/migrations/00003_create_poller_state_table.sql`**:
  ```sql
  -- +goose Up
  CREATE TABLE poller_state (
    id INTEGER PRIMARY KEY CHECK (id = 1), -- Enforce singleton row
    last_processed_key BLOB,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
  );

  -- +goose Down
  DROP TABLE IF EXISTS poller_state;
  ```

## 3. Implement Migration Logic in `db_init.go`

The `Connect` function in `backend/db/db_init.go` will be updated to automatically run migrations on startup.

The new logic will:
1.  Add a new `embed.FS` variable to hold the embedded migration files.
2.  In the `Connect` function, after the database connection is established:
    -   Set the Goose dialect to `sqlite3`.
    -   Configure Goose to use the embedded filesystem.
    -   Call `goose.Up` to apply all pending migrations.
3.  The old `initializeTables` function will be removed.

## 4. Remove Old Schema Files

Once the new migration files are in place, the old `schema.sql` files in `backend/db/users`, `backend/db/api_keys`, and `backend/db/state` will be deleted.