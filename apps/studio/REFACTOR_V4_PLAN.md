# Junjo AI Studio V4 Refactor Plan

This document tracks the incremental refactor from V3 to V4 architecture as defined in [REFACTOR_V4_ARCHITECTURE.md](./REFACTOR_V4_ARCHITECTURE.md).

## Save Plans

- Save your plans with REFACTOR_V4_PLAN_XXX_NAME.md
- ex: REFACTOR_V4_PLAN_001_WAL.md

## Methodology

- Piece-by-piece implementation with validation at each stage
- Each component is tested independently before moving to the next
- Backwards compatibility is NOT required (greenfield V4)
- Existing data will be wiped for fresh V4 install

## Plan Documents

| # | Document | Status | Description |
|---|----------|--------|-------------|
| 001 | [WAL Replacement](./REFACTOR_V4_PLAN_001_WAL.md) | ✅ Complete | Replaced BadgerDB with SQLite WAL in Go ingestion |
| 002 | [Parquet Flush](./REFACTOR_V4_PLAN_002_PARQUET_FLUSH.md) | ✅ Complete | Background flusher writes spans to Parquet files |
| 003 | TBD | ⏳ Pending | Python backend Parquet indexer |
| 004 | TBD | ⏳ Pending | DataFusion query engine |
| 005 | TBD | ⏳ Pending | LanceDB vector search |
| 006 | TBD | ⏳ Pending | Query orchestrator (live + historical merge) |

## Current Focus

**002 - Parquet Flush** ✅: Implemented background flusher that reads spans from SQLite, converts to Arrow format, writes ZSTD-compressed Parquet files with date partitioning, deletes flushed spans, and tracks flush state.

## Architecture Overview (V4)

```
Client App → Go Ingestion (SQLite WAL) → Parquet Files → Python Backend (DuckDB metadata + DataFusion queries)
```

See [REFACTOR_V4_ARCHITECTURE.md](./REFACTOR_V4_ARCHITECTURE.md) for complete architecture details.
