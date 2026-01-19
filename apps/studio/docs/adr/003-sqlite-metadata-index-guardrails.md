# ADR-003: SQLite Metadata Index Guardrails

## Status
Accepted

## Context

After replacing DuckDB metadata indexing with a SQLite metadata index, several implementation details become critical for correctness and performance:

- The metadata DB already contains the **cold-tier** service set (`file_services`). Scanning cold Parquet files to compute distinct services is unnecessary and can become expensive as cold storage grows.
- The Parquet storage layout is **partitioned** (`year=*/month=*/day=*`) and includes ephemeral `tmp/` files; maintenance scans must match the indexer scan rules to avoid deleting valid index rows.
- SQLite page cache is **per connection**. If thread-local connections are created across an unbounded thread pool, memory usage scales with thread count.
- SQLite `VACUUM` cannot run inside an active transaction.
- Timestamp comparisons rely on consistent UTC ISO8601 formatting for correct lexicographic ordering.

## Decision

Adopt the following guardrails for the SQLite metadata index:

1. **Distinct service list**
   - **COLD**: `SELECT DISTINCT service_name FROM file_services ORDER BY service_name`
   - **HOT**: read `hot_snapshot.parquet` only, compute distinct service names, then union in Python

2. **Filesystem sync**
   - Use the same recursive scan logic as the Parquet indexer (partitioned directories, skip `tmp/`) when reconciling `parquet_files` with disk.

3. **Bounded background indexing**
   - Run the Parquet background indexer on a bounded executor (single worker) to prevent creating many thread-local SQLite connections and multiplying page caches.

4. **Immediate indexing notifications**
   - The ingestion `NotifyNewParquetFile` hook must trigger a single indexing pass safely (serialized with the background indexer) to avoid the “cold file exists but metadata not indexed yet” gap.

5. **PrepareHotSnapshot semantics**
   - When there are no unflushed spans, the ingestion service may return `success=true` with an **empty** `snapshot_path`.
   - The backend must treat an empty `snapshot_path` (or `row_count=0`) as “no HOT tier available” and skip reading the snapshot.

6. **VACUUM ordering**
   - Commit deletes before running `VACUUM`.

7. **Timestamp consistency**
   - Store and compare times in UTC ISO8601 with timezone (`+00:00`).

## Consequences

- Service discovery stays fast and avoids scanning cold Parquet files.
- Startup sync cannot accidentally wipe the index due to mismatched scan rules.
- Metadata memory usage stays predictable as concurrency increases.

## Related

- `ingestion/adr/002-sqlite-metadata-index.md`
- `METADATA_REFACTOR.md`
