CREATE TABLE IF NOT EXISTS poller_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  -- Enforce a single row
  last_key BLOB
);