-- SQLite Metadata Index Schema
--
-- Per-trace indexing for Parquet files, replacing DuckDB's per-span indexing.
-- 50-100x memory reduction by indexing traces instead of spans.
--
-- Tables:
--   parquet_files: File registry with time bounds
--   trace_files: trace_id -> file_id mapping (critical lookup)
--   file_services: file_id -> service_name mapping
--   llm_traces: service -> trace_ids with LLM spans
--   workflow_files: service -> file_ids with workflows
--   failed_parquet_files: Error tracking

-- ============================================================================
-- parquet_files: File registry
-- ============================================================================
CREATE TABLE IF NOT EXISTS parquet_files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    min_time TEXT NOT NULL,  -- ISO8601 timestamp
    max_time TEXT NOT NULL,  -- ISO8601 timestamp
    row_count INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Index for time range pruning (queries filter by time range)
CREATE INDEX IF NOT EXISTS idx_parquet_files_time_range
    ON parquet_files(max_time DESC, min_time);

-- ============================================================================
-- trace_files: Trace to file mapping (critical lookup)
-- ============================================================================
CREATE TABLE IF NOT EXISTS trace_files (
    trace_id TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    PRIMARY KEY (trace_id, file_id),
    FOREIGN KEY (file_id) REFERENCES parquet_files(file_id) ON DELETE CASCADE
);

-- Index for trace lookup (the primary use case)
CREATE INDEX IF NOT EXISTS idx_trace_files_trace_id
    ON trace_files(trace_id);

-- Index for CASCADE delete performance
CREATE INDEX IF NOT EXISTS idx_trace_files_file_id
    ON trace_files(file_id);

-- ============================================================================
-- file_services: Service to file mapping
-- ============================================================================
CREATE TABLE IF NOT EXISTS file_services (
    file_id INTEGER NOT NULL,
    service_name TEXT NOT NULL,
    span_count INTEGER NOT NULL DEFAULT 0,
    min_time TEXT,  -- ISO8601 timestamp
    max_time TEXT,  -- ISO8601 timestamp
    PRIMARY KEY (file_id, service_name),
    FOREIGN KEY (file_id) REFERENCES parquet_files(file_id) ON DELETE CASCADE
);

-- Index for service queries
CREATE INDEX IF NOT EXISTS idx_file_services_service
    ON file_services(service_name);

-- ============================================================================
-- llm_traces: LLM trace optimization
-- ============================================================================
-- Stores trace_ids that contain at least one LLM span.
-- No FK to parquet_files since traces can span multiple files.
CREATE TABLE IF NOT EXISTS llm_traces (
    service_name TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    PRIMARY KEY (service_name, trace_id)
);

-- Index for LLM filter queries
CREATE INDEX IF NOT EXISTS idx_llm_traces_service
    ON llm_traces(service_name);

-- ============================================================================
-- workflow_files: Workflow file optimization
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflow_files (
    service_name TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    PRIMARY KEY (service_name, file_id),
    FOREIGN KEY (file_id) REFERENCES parquet_files(file_id) ON DELETE CASCADE
);

-- Index for workflow filter queries
CREATE INDEX IF NOT EXISTS idx_workflow_files_service
    ON workflow_files(service_name);

-- ============================================================================
-- failed_parquet_files: Error tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS failed_parquet_files (
    file_path TEXT PRIMARY KEY,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    file_size INTEGER,
    failed_at TEXT NOT NULL DEFAULT (datetime('now')),
    retry_count INTEGER NOT NULL DEFAULT 1
);

-- Index for reviewing recent failures
CREATE INDEX IF NOT EXISTS idx_failed_files_time
    ON failed_parquet_files(failed_at DESC);
