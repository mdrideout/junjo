# Metadata Index: Trace-Level SQLite Index

## Overview

This document describes the SQLite-based span metadata index layer. The goal is to keep memory usage ~15-30MB while maintaining query performance, enabling production deployment on 1GB VMs.

## Table of Contents

1. [Legacy Architecture (Removed)](#legacy-architecture-removed)
2. [Problem Statement](#problem-statement)
3. [Proposed Architecture](#proposed-architecture)
4. [Schema Design](#schema-design)
5. [Index Strategy](#index-strategy)
6. [Connection Management](#connection-management)
7. [Query Patterns](#query-patterns)
8. [Async Integration](#async-integration)
9. [Retention and Cleanup](#retention-and-cleanup)
10. [Migration Status](#migration-status)
11. [File Changes](#file-changes)
12. [Memory Analysis](#memory-analysis)

---

## Legacy Architecture (Removed)

A legacy implementation used a per-span metadata index with three tables:

| Table | Rows | Purpose | Memory |
|-------|------|---------|--------|
| `parquet_files` | ~10K | File registry with time bounds | ~2 MB |
| `span_metadata` | **Millions** | Per-span index (trace_id, is_root, etc.) | **100-300 MB** |
| `file_services` | ~1K | Service-to-file junction | ~50 KB |

The `span_metadata` table stores **one row per span**, which is the primary memory consumer.

---

## Problem Statement

### Memory Scaling Issue

| Data Volume | Spans | Legacy Index Memory |
|-------------|-------|---------------|
| 1 GB Parquet | 1M | ~100 MB |
| 10 GB Parquet | 10M | ~1 GB |
| 100 GB Parquet | 100M | ~10 GB |

On a 1GB VM with the full stack (ingestion ~150MB, backend ~250MB, frontend ~50MB), only ~400MB remains for the metadata index. The current architecture fails at ~10GB of telemetry data.

### Root Cause: Per-Span Indexing

The current design indexes every span individually. However, analysis of query patterns shows we only need:
- `trace_id → file_paths` (which files contain a trace)
- `service → file_paths` (which files contain a service)
- Semantic filters (LLM traces, workflow files)

We never query "which file contains span X" directly. The endpoint `GET /traces/{trace_id}/spans/{span_id}` fetches the entire trace and filters in Python.

---

## Proposed Architecture

Replace per-span indexing with per-trace indexing:

```
┌─────────────────────────────────────────────────────────────┐
│                    SQLite Metadata Index                    │
├─────────────────────────────────────────────────────────────┤
│  parquet_files     │ File registry (path, time bounds)      │
│  trace_files       │ trace_id → file_id mapping             │
│  file_services     │ file_id → service_name mapping         │
│  llm_traces        │ service → trace_ids with LLM spans     │
│  workflow_files    │ service → file_ids with workflows      │
│  failed_files      │ Files that failed to index             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    DataFusion (unchanged)                   │
│  Queries Parquet files using paths from SQLite index        │
└─────────────────────────────────────────────────────────────┘
```

### Size Comparison

| Scenario | Legacy per-span index | SQLite trace_files |
|----------|---------------------|-------------------|
| 1M spans, 20K traces | 100 MB | 2 MB |
| 10M spans, 200K traces | 1 GB | 20 MB |
| 100M spans, 2M traces | 10 GB | 200 MB |

**50-100x memory reduction** by indexing traces instead of spans.

---

## Schema Design

### Tables

**parquet_files** - File registry
- `file_id`: Primary key (autoincrement)
- `file_path`: Unique path to Parquet file
- `min_time`, `max_time`: Time bounds for pruning
- `row_count`, `size_bytes`: File statistics
- `indexed_at`: Timestamp

**trace_files** - Trace to file mapping (critical lookup)
- `trace_id`: 32-char trace identifier
- `file_id`: Foreign key to parquet_files
- Primary key: (trace_id, file_id)
- CASCADE delete when file removed

**file_services** - Service to file mapping
- `file_id`: Foreign key to parquet_files
- `service_name`: Service identifier
- Primary key: (file_id, service_name)
- CASCADE delete when file removed

**llm_traces** - LLM trace optimization
- `service_name`: Service identifier
- `trace_id`: Trace containing LLM span
- Primary key: (service_name, trace_id)

**workflow_files** - Workflow file optimization
- `service_name`: Service identifier
- `file_id`: File containing workflow spans
- Primary key: (service_name, file_id)
- CASCADE delete when file removed

**failed_parquet_files** - Error tracking
- `file_path`: Primary key
- `error_type`, `error_message`: Error details
- `file_size`, `failed_at`, `retry_count`: Metadata

---

## Index Strategy

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| `idx_trace_files_trace_id` | trace_files | trace_id | O(log n) trace lookup |
| `idx_trace_files_file_id` | trace_files | file_id | CASCADE delete performance |
| `idx_file_services_service` | file_services | service_name | Service queries |
| `idx_parquet_files_time_range` | parquet_files | max_time DESC, min_time | Time pruning |
| `idx_llm_traces_service` | llm_traces | service_name | LLM filter |
| `idx_workflow_files_service` | workflow_files | service_name | Workflow filter |
| `idx_failed_files_time` | failed_parquet_files | failed_at DESC | Failure review |

All primary lookups are O(log n) with B-tree indexes.

---

## Connection Management

### SQLite Configuration

| Pragma | Value | Purpose |
|--------|-------|---------|
| `journal_mode` | WAL | Concurrent reads, non-blocking writes |
| `synchronous` | NORMAL | Faster commits, safe with WAL |
| `cache_size` | -10000 | 10 MB page cache |
| `temp_store` | MEMORY | Temp tables in RAM |
| `mmap_size` | 50000000 | 50 MB memory-mapped I/O |
| `foreign_keys` | ON | Enforce CASCADE deletes |

### Thread-Local Connections

SQLite connections are stored in thread-local storage for thread safety. WAL mode enables:
- Multiple concurrent readers
- Single writer (non-blocking to readers)
- Consistent read snapshots

**Important:** SQLite page cache is per-connection. If thread-local connections are created across an unbounded thread pool, memory usage scales with the number of threads. Background indexing should use a **bounded** executor (single worker) to keep connection count and memory stable.

### File Organization

```
.dbdata/
├── sqlite/
│   ├── junjo.db      # User data (auth, API keys) - existing
│   └── metadata.db   # Span metadata index - NEW
├── spans/
│   ├── parquet/      # Cold tier Parquet files
│   ├── wal/          # Arrow IPC WAL segments
│   └── hot_snapshot.parquet
```

Separate databases because:
- `junjo.db` is critical user data (cannot rebuild)
- `metadata.db` can be rebuilt from Parquet files
- Different backup/retention strategies

---

## Query Patterns

### API Endpoints and Index Usage

| Endpoint | SQLite Query | DataFusion Query |
|----------|--------------|------------------|
| `GET /services` | `SELECT DISTINCT service_name FROM file_services` | `SELECT DISTINCT service_name FROM hot_snapshot` (HOT only) |
| `GET /services/{svc}/spans` | `SELECT file_path ... WHERE service_name = ?` | `WHERE service_name = ?` |
| `GET /services/{svc}/spans/root` | `SELECT file_path ... WHERE service_name = ?` | `WHERE parent_span_id IS NULL` |
| `GET /services/{svc}/spans/root?has_llm=true` | `llm_traces` membership for candidate trace_ids | Query root spans, then filter using COLD+HOT LLM trace sets |
| `GET /services/{svc}/workflows` | `SELECT file_path FROM workflow_files WHERE service = ?` | `WHERE junjo.span_type = 'workflow'` |
| `GET /traces/{trace_id}/spans` | `SELECT file_path ... WHERE trace_id = ?` | `WHERE trace_id = ?` |
| `GET /traces/{tid}/spans/{sid}` | `SELECT file_path ... WHERE trace_id = ?` | Filter by span_id in Python |

### Query Performance

All SQLite queries are sub-millisecond with proper indexes:
- B-tree index lookup: O(log n)
- 200K traces → ~17 comparisons
- Expected latency: < 1ms

---

## Async Integration

SQLite is synchronous. The backend uses async Python (FastAPI + asyncio).

### Pattern: run_in_executor

```
async def get_files_for_trace(trace_id: str) -> list[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor,  # Bounded ThreadPoolExecutor (recommended for background tasks)
        metadata_repository.get_file_paths_for_trace,
        trace_id
    )
```

For request-time lookups, the metadata queries are sub-millisecond and can be run directly or offloaded depending on the latency budget. For background indexing, always use a bounded executor to avoid creating many thread-local SQLite connections.

---

## Retention and Cleanup

### Time-Based Retention

Remove files older than N days:
1. `DELETE FROM parquet_files WHERE max_time < cutoff`
2. CASCADE deletes clean up trace_files, file_services, workflow_files
3. Separate cleanup for llm_traces (no FK)
4. `VACUUM` to reclaim space (must run outside a transaction; commit deletes first)

### Filesystem Sync

On startup, sync index with filesystem:
1. Recursively scan Parquet directory for existing files (match indexer scan rules, skip `tmp/`)
2. Remove index entries for deleted files
3. Queue missing files for re-indexing

### Rebuild from Scratch

Since all data derives from Parquet files:
1. Clear all tables
2. Scan Parquet directory
3. Re-index each file

Useful for schema migrations or corruption recovery.

---

## Migration Status

This refactor is complete:
- The legacy per-span metadata index has been removed from the codebase.
- The metadata index is `metadata.db` (SQLite) and can be rebuilt from Parquet files.
- No backward compatibility is maintained for legacy index data.

---

## File Changes

### Create

```
backend/app/db_sqlite/metadata/
├── schema.sql        # Table definitions
├── db.py             # Connection management
├── repository.py     # Query functions
├── indexer.py        # Indexing logic
├── maintenance.py    # Cleanup/retention
└── __init__.py       # Module exports
```

### Modify

```
backend/app/main.py                           # Initialize metadata DB
backend/app/features/otel_spans/repository.py # Use SQLite lookups
backend/app/features/parquet_indexer/background_indexer.py  # Use SQLite indexer
backend/app/config/settings.py                # Add metadata_db_path
```

### Query Engine

```
backend/app/features/otel_spans/datafusion_query.py  # DataFusion two-tier queries (COLD + HOT)
```

---

## Memory Analysis

### SQLite Memory Budget

| Component | Memory |
|-----------|--------|
| Page cache (`cache_size=-10000`) | 10 MB |
| Memory-mapped I/O (`mmap_size`) | OS-managed |
| Statement cache | < 1 MB |
| WAL buffers | ~1 MB |
| **Total SQLite** | **~12 MB** |

### Index Data Size (on disk, cached as needed)

| Data | Rows | Disk Size |
|------|------|-----------|
| 100K files | 100K | ~10 MB |
| 2M traces | 2M | ~100 MB |
| Services | < 1K | < 1 MB |

### Comparison

| Component | Legacy per-span index | SQLite trace-level index |
|-----------|-----------------------|--------------------------|
| span_metadata (2M rows) | ~200 MB | N/A |
| trace_files (200K rows) | N/A | ~10 MB cache |
| parquet_files (10K rows) | ~2 MB | ~1 MB |
| **Total working memory** | **~250 MB** | **~15 MB** |

**10-20x memory reduction** enables deployment on 1GB VMs.

---

## Concurrency Model

```
┌─────────────────────────────────────────────────────────────┐
│                     SQLite WAL Mode                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Reader 1 ──┐                                              │
│   Reader 2 ──┼──► WAL Snapshot (consistent reads)           │
│   Reader N ──┘         ▲                                    │
│                        │                                    │
│                   ┌────┴─────┐                              │
│                   │  Writer  │ (Background indexer)         │
│                   └──────────┘                              │
│                                                             │
│   • Multiple readers access simultaneously                  │
│   • Single writer doesn't block readers                     │
│   • Readers see consistent snapshot                         │
│   • Writer acquires lock only during commit                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Transaction Safety

Indexing a new file is atomic:
1. `BEGIN IMMEDIATE` (acquire write lock)
2. Insert file metadata
3. Insert trace mappings
4. Insert service mappings
5. Insert LLM/workflow optimizations
6. `COMMIT` (or `ROLLBACK` on error)

All-or-nothing: partial index entries cannot exist.

---

## HOT Tier Handling

The SQLite index only covers COLD tier (flushed Parquet files).

HOT tier (unflushed WAL snapshot):
- Created on-demand via `PrepareHotSnapshot` RPC
- Not indexed in SQLite (ephemeral)
- DataFusion queries it directly

Query flow unchanged:
1. Get COLD file paths from SQLite
2. Get HOT snapshot path from gRPC
3. DataFusion queries both
4. Deduplicate (COLD > HOT)

---

## Summary

| Aspect | Legacy (Per-Span Metadata Index) | Current (SQLite Trace-Level Index) |
|--------|----------------------------------|------------------------------------|
| Memory usage | 200-300 MB | 15-30 MB |
| Dependencies | Extra embedded DB engine | sqlite3 (stdlib) |
| Already in stack | No | Yes (user data) |
| Point lookups | Good | Excellent |
| Analytical queries | N/A (use DataFusion) | N/A (use DataFusion) |
| Concurrency | Good | Good (WAL mode) |
| Can rebuild from Parquet | Yes | Yes |
| Scales to 10M traces | Memory issues | No problem |

SQLite is the right choice because:
1. Point lookups are the primary use case
2. DataFusion handles analytical queries on Parquet
3. 10-20x memory reduction enables 1GB VM deployment
4. Already in the stack for user authentication
5. Simpler dependency tree
