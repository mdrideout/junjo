-- V4 Schema: failed_parquet_files
-- Tracks files that failed to index (corrupt, malformed, etc.)
-- Prevents retry loops and enables debugging/reporting.

CREATE TABLE IF NOT EXISTS failed_parquet_files (
    file_path TEXT PRIMARY KEY,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    file_size BIGINT,
    failed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    retry_count INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_failed_files_failed_at
    ON failed_parquet_files (failed_at DESC);
