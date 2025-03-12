CREATE TABLE node_logs (
  id text PRIMARY KEY NOT NULL UNIQUE,
  exec_id text NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('start', 'end')),
  event_time_nano INTEGER NOT NULL,
  -- allows for nanosecond precision
  ingestion_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  state JSONB NOT NULL
);