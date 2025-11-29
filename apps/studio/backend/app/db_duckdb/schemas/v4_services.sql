-- V4 Schema: services
-- Service catalog for quick lookups and aggregated stats.
-- Updated by the Parquet indexer as new files are indexed.

CREATE TABLE IF NOT EXISTS services (
    service_name TEXT PRIMARY KEY,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    total_spans BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_services_last_seen
    ON services (last_seen DESC);
