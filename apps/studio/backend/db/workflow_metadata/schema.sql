CREATE TABLE workflow_metadata (
  id text PRIMARY KEY NOT NULL UNIQUE,
  exec_id text NOT NULL UNIQUE,
  app_name text NOT NULL,
  workflow_name text NOT NULL,
  event_time_nano INTEGER NOT NULL,
  ingestion_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  structure JSONB NOT NULL
);

CREATE INDEX idx_workflow_metadata_app_name ON workflow_metadata (app_name);

CREATE INDEX idx_workflow_metadata_workflow_name ON workflow_metadata (workflow_name);

CREATE INDEX idx_workflow_metadata_ingestion_time ON workflow_metadata (ingestion_time);

CREATE INDEX idx_workflow_metadata_event_time_nano ON workflow_metadata (event_time_nano);