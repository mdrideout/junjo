-- Junjo AI Studio metadata index.
--
-- This file is the only source of the metadata schema. The index is derived
-- from cold Parquet files and is rebuildable: on a schema version mismatch the
-- backend deletes the database and the indexer rebuilds it.
--
-- The index answers "which cold files should DataFusion open?". It never
-- stores span payloads. See ingestion ADR-002.
--
-- Span time bounds are integer nanoseconds since the Unix epoch.

-- File registry with time bounds.
CREATE TABLE parquet_files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    min_time_ns INTEGER NOT NULL,
    max_time_ns INTEGER NOT NULL,
    row_count INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT (datetime('now'))
) STRICT;

CREATE INDEX idx_parquet_files_time_range
    ON parquet_files (max_time_ns DESC, min_time_ns);

-- trace_id -> file_id. The primary key serves trace lookups.
CREATE TABLE trace_files (
    trace_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    PRIMARY KEY (trace_id, file_id),
    FOREIGN KEY (file_id) REFERENCES parquet_files (file_id) ON DELETE CASCADE
) STRICT;

-- Serves the cascade delete from parquet_files.
CREATE INDEX idx_trace_files_file_id ON trace_files (file_id);

-- file_id -> service_name with per-service bounds.
CREATE TABLE file_services (
    file_id INTEGER NOT NULL,
    service_name TEXT NOT NULL,
    span_count INTEGER NOT NULL DEFAULT 0,
    min_time_ns INTEGER NOT NULL,
    max_time_ns INTEGER NOT NULL,
    PRIMARY KEY (file_id, service_name),
    FOREIGN KEY (file_id) REFERENCES parquet_files (file_id) ON DELETE CASCADE
) STRICT;

CREATE INDEX idx_file_services_service ON file_services (service_name);

-- Traces that contain at least one LLM span. No foreign key, because one
-- trace can span several files.
CREATE TABLE llm_traces (
    service_name TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    PRIMARY KEY (service_name, trace_id)
) STRICT;

-- Files that contain Workflow spans, per service.
CREATE TABLE workflow_files (
    service_name TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    PRIMARY KEY (service_name, file_id),
    FOREIGN KEY (file_id) REFERENCES parquet_files (file_id) ON DELETE CASCADE
) STRICT;

-- Files that contain Agent executable spans, per service.
CREATE TABLE agent_files (
    service_name TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    PRIMARY KEY (service_name, file_id),
    FOREIGN KEY (file_id) REFERENCES parquet_files (file_id) ON DELETE CASCADE
) STRICT;

-- Files that hold the owner span of a Workflow, Subflow, or Agent execution.
-- `executable` is a 64-bit hash of the service name, the span type, and the
-- runtime identity: see `executable_key` in the backend's metadata module.
-- This is the index's one table with a row per execution, so the row is two
-- integers and the table is its own primary key index.
CREATE TABLE executable_files (
    executable INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    PRIMARY KEY (executable, file_id),
    FOREIGN KEY (file_id) REFERENCES parquet_files (file_id) ON DELETE CASCADE
) STRICT, WITHOUT ROWID;

-- Serves the cascade delete from parquet_files.
CREATE INDEX idx_executable_files_file_id ON executable_files (file_id);

-- Files that failed to index. A file whose contents could not be read as
-- Parquet stays here and is not tried again. A file that failed on I/O or on
-- the index write (error_type 'Io' or 'Sqlite') is tried again every cycle,
-- and its row is removed when it is indexed.
CREATE TABLE failed_parquet_files (
    file_path TEXT PRIMARY KEY,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    file_size INTEGER,
    failed_at TEXT NOT NULL DEFAULT (datetime('now')),
    retry_count INTEGER NOT NULL DEFAULT 1
) STRICT;

CREATE INDEX idx_failed_files_time ON failed_parquet_files (failed_at DESC);
