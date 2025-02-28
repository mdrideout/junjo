CREATE TABLE workflow_metadata (
  id text PRIMARY KEY NOT NULL UNIQUE,
  exec_id text NOT NULL UNIQUE,
  name text NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  structure JSONB NOT NULL
);