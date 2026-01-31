# ADR-003: SQLite Metadata Index Guardrails

## Status
Accepted

## Context

After replacing the legacy per-span metadata index with a SQLite metadata index, several implementation details become critical for correctness and performance:

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

4. **Indexing is eventual (no tight coupling)**
   - The backend indexer polls the filesystem for new cold Parquet files and indexes them into SQLite metadata.
   - Ingestion must not depend on backend availability for cold flush correctness.

5. **Flush → index query bridge**
   - There is an unavoidable window where:
     - A new cold Parquet file exists on disk
     - The SQLite metadata index has not yet ingested it
     - The WAL may already be empty (so HOT snapshot is empty)
   - The ingestion service must return a bounded list of *recently flushed cold* Parquet file paths from `PrepareHotSnapshot`.
   - The backend must temporarily treat those `recent_cold_paths` as additional cold query sources until SQLite metadata catches up to prevent user-visible “No logs found” for very new traces/workflows.

6. **PrepareHotSnapshot semantics**
   - When there are no unflushed spans, the ingestion service may return `success=true` with an **empty** `snapshot_path`.
   - The backend must treat an empty `snapshot_path` (or `row_count=0`) as “no HOT tier available” and skip reading the snapshot.

7. **PrepareHotSnapshot throttling**
   - `PrepareHotSnapshot` can be expensive when the WAL is large and the UI issues multiple concurrent requests.
   - Throttle and cache snapshot creation inside the ingestion service for a short TTL (e.g. ~1s) and serialize snapshot creation to avoid stampedes.
   - The backend should call ingestion per request so it always receives up-to-date `recent_cold_paths` (the bridge) even when snapshot creation is cached.

8. **Bound cold file registration for service queries**
   - Service-scoped listing queries (services → workflows → traces) must register a bounded number of cold files (most recent N) independent of the requested span limit.
   - Rationale: the request `limit` is a row limit, not a file limit; coupling the two can accidentally register hundreds of files.

9. **DataFusion Parquet registration**
   - The Python DataFusion bindings may not reliably accept `register_parquet(table, [file1, file2, ...])`.
   - When registering many files, register each file path as its own table and `UNION ALL` them into a single logical table for queries.
   - **Pre-filter file paths** before registration:
     - must exist and be a regular file
     - must end with `.parquet`
     - must have `st_size > 0`
   - Rationale: the Python `register_parquet` call can succeed for missing/0-byte files and create a table with an **empty schema**, which later fails with planning errors like `column 'service_name' not found` and `valid_fields: []`.

10. **VACUUM ordering**
   - Commit deletes before running `VACUUM`.

11. **Timestamp consistency**
   - Store and compare times in UTC ISO8601 with timezone (`+00:00`).

## Consequences

- Service discovery stays fast and avoids scanning cold Parquet files.
- Startup sync cannot accidentally wipe the index due to mismatched scan rules.
- Metadata memory usage stays predictable as concurrency increases.

## Related

- `ingestion/adr/002-sqlite-metadata-index.md`
- `METADATA_REFACTOR.md`
