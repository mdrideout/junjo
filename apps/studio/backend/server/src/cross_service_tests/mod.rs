//! Tests that run this backend's code against the real ingestion service.
//!
//! Every test that needs ingestion starts its own process through `harness`,
//! sends spans to it over OTLP, and asserts through this backend's ingestion
//! client, span repository, or HTTP routes. The stand-in ingestion in
//! `test_support` answers what a test tells it to. These tests are where the
//! two services meet: the internal API, the Parquet files ingestion writes,
//! the hot snapshot, the recent-cold bridge, and the metadata index.
//!
//! The first of these tests to run builds ingestion's release binary. On a
//! clean checkout that takes minutes.

mod harness;
mod otlp;

mod api_key_filter;
mod flush_index_bridge;
mod flush_wal;
mod has_llm;
mod hot_snapshot;
mod hot_snapshot_flush_race;
mod hot_snapshot_sharing;
mod transport_contract;
