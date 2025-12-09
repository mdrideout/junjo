-- V4 Schema: file_services
-- Junction table mapping which services are in which Parquet files.
-- Enables efficient queries:
-- 1. "Which parquet files contain service X?" (for filtered DataFusion queries)
-- 2. "Which services have data in date range Y?" (via join with parquet_files)

CREATE TABLE IF NOT EXISTS file_services (
    file_id INTEGER NOT NULL REFERENCES parquet_files(file_id),
    service_name TEXT NOT NULL,
    span_count INTEGER NOT NULL,
    min_time TIMESTAMPTZ NOT NULL,
    max_time TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (file_id, service_name)
);

-- Index for service lookups: "Give me all files for service X"
CREATE INDEX IF NOT EXISTS idx_file_services_service
    ON file_services (service_name);

-- Index for time-range queries: "Which services have data in range?"
CREATE INDEX IF NOT EXISTS idx_file_services_time_range
    ON file_services (min_time, max_time);
