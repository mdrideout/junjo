# ADR-002: SQLite Metadata Index (Replacing Legacy Per-Span Index)

## Status
Accepted

## Context

The backend previously used a per-span metadata index for Parquet file lookups (trace and span queries). The legacy implementation stored **one row per span** in the `span_metadata` table.

### Problem: Memory Scaling

| Data Volume | Spans | Legacy Index Memory |
|-------------|-------|---------------|
| 1 GB Parquet | 1M | ~100 MB |
| 10 GB Parquet | 10M | ~1 GB |
| 100 GB Parquet | 100M | ~10 GB |

The entire Junjo AI Studio stack (ingestion ~150MB, backend ~250MB, frontend ~50MB) must run on a **1GB VM**. This leaves ~400MB for the metadata index. The current architecture fails at ~10GB of telemetry data.

### Root Cause: Per-Span Indexing

Analysis of actual query patterns shows we never need "which file contains span X" directly. The `GET /traces/{trace_id}/spans/{span_id}` endpoint fetches the entire trace and filters in Python. We only need:

- `trace_id → file_paths` (which files contain a trace)
- `service → file_paths` (which files contain a service)
- Semantic filters (LLM traces, workflow files)

Per-trace indexing is sufficient, providing **50-100x memory reduction**.

### Deployment Constraint

The 1GB VM constraint is non-negotiable. The ingestion service has already been optimized with Arrow IPC WAL and streaming Parquet writes to minimize memory. The metadata layer must follow suit.

## Decision

Replace the legacy per-span metadata index with **SQLite for metadata indexing**, changing from per-span to per-trace granularity.

### Architecture

SQLite indexes metadata with six tables:

| Table | Purpose | Size |
|-------|---------|------|
| `parquet_files` | File registry (path, time bounds) | ~10 KB per 1K files |
| `trace_files` | trace_id → file_id mapping | ~50 bytes per trace |
| `file_services` | file_id → service_name mapping | ~20 bytes per entry |
| `llm_traces` | Traces containing LLM spans | ~50 bytes per trace |
| `workflow_files` | Files containing workflows | ~20 bytes per entry |
| `failed_parquet_files` | Error tracking | Minimal |

DataFusion continues to handle actual Parquet queries. SQLite only provides "which files to query" — it never reads span content.

### Memory Budget

| Component | Memory |
|-----------|--------|
| SQLite page cache | 10 MB |
| Statement cache | < 1 MB |
| WAL buffers | ~1 MB |
| **Total** | **~12-15 MB** |

Compare to ~200-300 MB for the legacy per-span index at the same data volume.

### Query Flow

1. Frontend requests spans for a trace/service
2. Backend queries SQLite for relevant file paths
3. Backend calls `PrepareHotSnapshot` and uses:
   - HOT snapshot Parquet path (unflushed WAL)
   - `recent_cold_paths` (recently flushed cold Parquet files not yet indexed)
4. DataFusion queries SQLite-selected cold Parquet files + `recent_cold_paths` + HOT snapshot
5. Results returned to frontend

### Query Optimizations (Guardrails)

To avoid regressions that reintroduce large Parquet scans:

1. **Distinct service names**
   - **COLD**: Read from SQLite (`SELECT DISTINCT service_name FROM file_services`)
   - **HOT**: Scan only `hot_snapshot.parquet` and union in Python
   - Rationale: the metadata DB already contains the cold-tier service set; scanning all cold Parquet files is unnecessary.

2. **Bounded cold file registration for service-scoped queries**
   - Service-level queries must register a bounded number of cold files (e.g. most recent N files) to prevent DataFusion from loading an unbounded working set into memory.

### Operational Notes (Guardrails)

1. **PrepareHotSnapshot semantics**
   - When the WAL is empty, the ingestion service removes any prior snapshot file and returns `success=true` with an **empty** `snapshot_path`.
   - The backend must treat an empty `snapshot_path` (or `row_count=0`) as “no HOT tier available” and skip reading the snapshot.

2. **Filesystem sync must match the indexer scan**
   - Startup reconciliation must use the same recursive scan rules as the background indexer (partitioned directories, skip `tmp/` warm files).
   - Rationale: mismatched scans can incorrectly treat “files exist” as “no files” and delete valid index rows.

3. **Bound SQLite connection count**
   - Each SQLite connection has its own page cache; unlimited thread-local connections can multiply memory usage.
   - Background indexing should run on a bounded executor (single worker) to keep connection count (and memory) stable.

4. **VACUUM safety**
   - `VACUUM` must run outside an active transaction (commit deletes first).

5. **Timestamp consistency**
   - Store and compare timestamps consistently in UTC ISO8601 with timezone (`+00:00`) to keep lexicographic comparisons correct.

All SQLite queries are sub-millisecond with B-tree indexes. The 200K trace lookup requires ~17 B-tree comparisons.

## Alternatives Considered

### 1. Apache Iceberg

**Rejected.** Iceberg provides catalog-level metadata (file registration, schema evolution, time travel) but not secondary indexes. We would still need trace_id → file lookups. Iceberg adds complexity without solving the core problem. It's designed for distributed systems with S3/GCS storage — overkill for single-node, local-disk deployments.

### 2. Pure In-Memory Index

**Partially accepted.** A Python dictionary mapping trace_id to file_ids would work for small deployments (~500K traces). However:

- Memory grows linearly with trace count
- 2M traces × 50 bytes = 100 MB (acceptable)
- 20M traces × 50 bytes = 1 GB (exceeds budget)

Risk: Unpredictable memory growth as customers scale. We need bounded memory regardless of data volume.

### 3. Bloom Filters

**Considered.** Per-file Bloom filters could answer "does file X contain trace Y?" probabilistically. However:

- Requires checking all files for false negatives
- False positives cause unnecessary Parquet reads
- Still need authoritative trace → file mapping somewhere
- Complexity for uncertain gain

### 4. Keep the Legacy Index, Reduce Granularity

**Considered.** Keep the legacy index but index traces instead of spans. This reduces memory but:

- Higher baseline memory than SQLite
- Extra native dependency and build complexity
- SQLite is already in the stack for user data
- SQLite's simplicity is an advantage

### 5. LevelDB / RocksDB

**Considered.** LSM-tree databases optimized for write-heavy workloads. However:

- Another native dependency to build/manage
- More complex than SQLite for simple key-value lookups
- Write amplification is not a concern (low write volume)

## Consequences

### Positive

1. **10-20x memory reduction**: From 200-300 MB to 15-30 MB
2. **Predictable scaling**: Bounded memory regardless of span count
3. **Dependency consolidation**: SQLite already in stack for user data
4. **Simpler builds**: stdlib sqlite3 vs extra native dependency
5. **Rebuildable**: Index derives from Parquet files, can always regenerate
6. **Battle-tested concurrency**: SQLite WAL mode provides consistent reads during writes

### Negative

1. **Migration effort**: Dual-write period, phased rollout
2. **Two databases**: junjo.db (user data) + metadata.db (span index)
3. **Sync complexity**: Must sync with filesystem on startup
4. **No analytical queries**: aggregations now require DataFusion

### Neutral

1. **Query performance**: Both provide sub-millisecond B-tree lookups
2. **Durability**: Both use WAL for crash safety
3. **Concurrency**: WAL mode enables concurrent reads in both

## Migration Path

1. **Phase 1**: Create metadata.db alongside the legacy index, dual-write
2. **Phase 2**: Read from SQLite, verify consistency
3. **Phase 3**: Remove legacy index dependency and code
4. **Phase 4**: Delete legacy index database files

Rollback is possible at any phase by reverting to legacy index reads.

## Related

- METADATA_REFACTOR.md: Complete implementation details with schema and queries
- ADR-001: Segmented WAL architecture (ingestion layer)
- SQLite WAL mode: https://sqlite.org/wal.html
- DataFusion: https://datafusion.apache.org/
