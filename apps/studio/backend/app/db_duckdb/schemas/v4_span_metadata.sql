-- V4 Schema: span_metadata
-- Lightweight span data for listings and navigation.
-- Full span data (attributes, events) stays in Parquet files.

CREATE TABLE IF NOT EXISTS span_metadata (
    span_id VARCHAR(32) PRIMARY KEY,
    trace_id VARCHAR(32) NOT NULL,
    parent_span_id VARCHAR(32),
    service_name TEXT NOT NULL,
    name TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    duration_ns BIGINT NOT NULL,
    status_code TINYINT NOT NULL DEFAULT 0,
    span_kind TINYINT NOT NULL DEFAULT 0,
    is_root BOOLEAN NOT NULL DEFAULT FALSE,
    junjo_span_type VARCHAR(32),  -- workflow, subflow, node, run_concurrent, or empty
    file_id INTEGER REFERENCES parquet_files(file_id)
);

CREATE INDEX IF NOT EXISTS idx_span_metadata_trace
    ON span_metadata (trace_id);

CREATE INDEX IF NOT EXISTS idx_span_metadata_service_time
    ON span_metadata (service_name, start_time DESC);

CREATE INDEX IF NOT EXISTS idx_span_metadata_time
    ON span_metadata (start_time DESC);

CREATE INDEX IF NOT EXISTS idx_span_metadata_root_time
    ON span_metadata (is_root, start_time DESC);

CREATE INDEX IF NOT EXISTS idx_span_metadata_file
    ON span_metadata (file_id);

CREATE INDEX IF NOT EXISTS idx_span_metadata_junjo_type
    ON span_metadata (junjo_span_type, service_name, start_time DESC);
