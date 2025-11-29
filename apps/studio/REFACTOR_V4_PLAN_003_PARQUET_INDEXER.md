# Plan 003: Python Backend Parquet Indexer

## Status: ✅ Complete

## Overview

Implement a background worker in the Python backend that polls the local filesystem for new Parquet files (written by Go ingestion), extracts span summaries, and indexes them into DuckDB metadata tables.

**Replaces:** The existing `span_ingestion_poller` that polls Go via gRPC. In V4, data flows via Parquet files on shared storage.

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Checkpoint storage | Derive from DuckDB | Query `parquet_files` table - no separate state needed |
| File discovery | Directory scan + DuckDB check | Scan filesystem, check if `file_path` exists in `parquet_files` |
| DuckDB schema | `parquet_files` + `span_metadata` | Metadata for listing, full data stays in Parquet |
| Parquet reading | pyarrow | Standard Python library for Parquet |
| Hot data | Keep gRPC client to ingestion | Query unflushed spans from Go SQLite WAL |

---

## DuckDB V4 Schema

### parquet_files (indexed file registry)
- `file_id` INTEGER PRIMARY KEY
- `file_path` TEXT UNIQUE NOT NULL (used for deduplication/checkpoint)
- `service_name`, `min_time`, `max_time`, `row_count`, `size_bytes`, `indexed_at`

### span_metadata (lightweight span data for listings)
- `span_id` VARCHAR(32) PRIMARY KEY
- `trace_id`, `parent_span_id`, `service_name`, `name`
- `start_time`, `end_time`, `duration_ns`, `status_code`, `span_kind`
- `is_root` BOOLEAN, `file_id` FK

### services (catalog)
- `service_name` TEXT PRIMARY KEY
- `first_seen`, `last_seen`, `total_spans`

**No separate SQLite checkpoint table** - derive from `parquet_files.file_path`

---

## Implementation Phases

### Phase 1: Configuration ✅
- Add `ParquetIndexerSettings` to settings.py
- Settings: `JUNJO_SPAN_STORAGE_PATH`, `INDEXER_POLL_INTERVAL`, `INDEXER_BATCH_SIZE`

### Phase 2: DuckDB V4 Schema ✅
- Create SQL files: `v4_parquet_files.sql`, `v4_span_metadata.sql`, `v4_services.sql`
- Update `initialize_tables()` to create V4 schema (comment out V3 tables)

### Phase 3: File Scanner Module ✅
- `scan_parquet_files(base_path)` - walks directory tree, returns all `.parquet` files
- Returns list of `ParquetFileInfo(path, mtime, size_bytes)`

### Phase 4: Parquet Reader Module ✅
- `read_parquet_metadata(path, size_bytes)` - reads metadata columns only (not attributes/events JSON)
- Returns `ParquetFileData` with list of `SpanMetadata`

### Phase 5: DuckDB V4 Repository ✅
- `is_file_indexed(file_path)` - check if file already in `parquet_files`
- `get_indexed_file_paths()` - return set of all indexed paths (for batch checking)
- `register_parquet_file(file_data)` - insert into `parquet_files`, return file_id
- `batch_insert_span_metadata(file_id, spans)` - insert span metadata rows
- `upsert_service(service_name, time, count)` - update service catalog

### Phase 6: Background Indexer ✅
- Async loop: scan files → filter unindexed (via DuckDB) → read/index each → repeat
- Error handling: log bad files with full context (path, error type, message), skip, continue
- Graceful shutdown on cancellation

### Phase 7: Integration ✅
- Start indexer task in `main.py` lifespan
- Comment out old `span_ingestion_poller` (keep gRPC client for hot data queries)

### Phase 8: Testing
- Unit tests for file_scanner, parquet_reader (deferred - basic import/lint tests passing)
- Integration tests for full indexing flow (deferred)

---

## New Files

| File | Purpose |
|------|---------|
| `backend/app/db_duckdb/schemas/v4_parquet_files.sql` | File registry DDL |
| `backend/app/db_duckdb/schemas/v4_span_metadata.sql` | Span metadata DDL |
| `backend/app/db_duckdb/schemas/v4_services.sql` | Service catalog DDL |
| `backend/app/db_duckdb/v4_repository.py` | V4 DuckDB operations |
| `backend/app/features/parquet_indexer/__init__.py` | Package init |
| `backend/app/features/parquet_indexer/file_scanner.py` | Filesystem scanning |
| `backend/app/features/parquet_indexer/parquet_reader.py` | Parquet reading |
| `backend/app/features/parquet_indexer/background_indexer.py` | Main loop |

## Files Modified

| File | Changes |
|------|---------|
| `backend/app/config/settings.py` | Add ParquetIndexerSettings |
| `backend/app/db_duckdb/db_config.py` | Update initialize_tables() for V4 |
| `backend/app/main.py` | Start indexer, comment out old poller |
| `docker-compose.yml` | Add SPAN_STORAGE_PATH to both services |

## Dependencies

- Added `pyarrow` to backend (via `uv add pyarrow`)

---

## Docker Configuration

Both services share `/app/.dbdata` via the same volume mount:
```yaml
volumes:
  - ${JUNJO_HOST_DB_DATA_PATH:-./.dbdata}:/app/.dbdata
```

**Storage Path Strategy** (following existing pattern):
- Users configure `JUNJO_HOST_DB_DATA_PATH` on the HOST (default: `./.dbdata`)
- Container paths are hardcoded in docker-compose.yml environment section
- Consistent with how `JUNJO_SQLITE_PATH` and `JUNJO_DUCKDB_PATH` work

**docker-compose.yml changes:**

Ingestion service - add to environment:
```yaml
- SPAN_STORAGE_PATH=/app/.dbdata/spans
```

Backend service - add to environment:
```yaml
- JUNJO_SPAN_STORAGE_PATH=/app/.dbdata/spans
```

**Python settings default:** `../.dbdata/spans` (relative, for local dev without Docker)

---

## V3 Code Handling

Per user preference - **disable V3 code but don't delete yet**:

1. **DuckDB**: Comment out V3 table initialization, add V4 tables alongside
2. **Span Ingestion Poller**: Comment out task creation in `main.py` lifespan
3. **Keep files in place**: No file deletions in this plan

---

## Deferred to Plan 004

- `daily_stats` table and aggregation logic (will add with DataFusion integration)
