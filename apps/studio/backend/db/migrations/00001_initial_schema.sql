-- File: db/migrations/00001_initial_schema.sql
-- +goose Up
-- This section defines the changes to apply.
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users (email);

CREATE TABLE api_keys (
  id TEXT PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE poller_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  -- Enforce a single row
  last_key BLOB
);

-- +goose Down
-- This section defines how to reverse the changes.
DROP TABLE users;

DROP TABLE api_keys;

DROP TABLE poller_state;