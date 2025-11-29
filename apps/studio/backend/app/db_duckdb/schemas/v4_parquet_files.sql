-- V4 Schema: parquet_files
-- Registry of indexed Parquet files. Used for:
-- 1. Deduplication (don't re-index same file)
-- 2. File-to-span mapping (know which file contains which spans)
-- 3. Time range queries (prune files by time)

CREATE SEQUENCE IF NOT EXISTS parquet_files_seq START 1;

CREATE TABLE IF NOT EXISTS parquet_files (
    file_id INTEGER PRIMARY KEY DEFAULT nextval('parquet_files_seq'),
    file_path TEXT UNIQUE NOT NULL,
    service_name TEXT NOT NULL,
    min_time TIMESTAMPTZ NOT NULL,
    max_time TIMESTAMPTZ NOT NULL,
    row_count INTEGER NOT NULL,
    size_bytes BIGINT NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parquet_files_time_range
    ON parquet_files (min_time, max_time);

CREATE INDEX IF NOT EXISTS idx_parquet_files_service
    ON parquet_files (service_name);
