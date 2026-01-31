# Ingestion Service (Rust)

The ingestion service is the high-throughput receiver for OTLP spans. It validates API keys, writes spans to a local WAL, and produces Parquet files for the backend to query.

## Architecture (Why)

- **Fast writes**: Incoming spans are appended to an Arrow IPC WAL (segmented files) for durable, low-overhead ingestion.
- **Queryable storage**: The WAL is periodically flushed to date-partitioned Parquet files for efficient scans.
- **Real-time reads**: The backend can request a hot snapshot (`PrepareHotSnapshot`) to query unflushed spans without streaming data over gRPC.
- **Fail-closed auth**: API keys are validated against the backend’s internal gRPC auth service and cached in-memory in ingestion for low latency.

Relevant ADRs:
- `ingestion/adr/001-segmented-wal-architecture.md`
- `ingestion/adr/002-sqlite-metadata-index.md`

## Protos

Rust codegen happens at build time via `ingestion/build.rs` from the shared `proto/` directory. No generated Rust code is committed to git.

## Running

For the standard workflow, run via `docker-compose.yml` from the repository root (recommended).

For local-native runs, `cargo run` requires `protoc` to be available on your PATH (see `PROTO_VERSIONS.md`).

Configuration is via environment variables; see `.env.example` and `ingestion/src/config.rs` for the full list.

## Testing

Run ingestion unit/integration tests:

```bash
cd ingestion
cargo test
```

Some backend integration tests also start the ingestion binary; see `backend/tests/conftest.py`.

