# Junjo AI Studio V4 Refactor Plan

This document tracks the incremental refactor from V3 to V4 architecture as defined in [REFACTOR_V4_ARCHITECTURE.md](./REFACTOR_V4_ARCHITECTURE.md).

## Methodology

- Piece-by-piece implementation with validation at each stage
- Each component is tested independently before moving to the next
- Backwards compatibility is NOT required (greenfield V4)
- Existing data will be wiped for fresh V4 install

## Plan Documents

| # | Document | Status | Description |
|---|----------|--------|-------------|
| 001 | [WAL Replacement](./REFACTOR_V4_PLAN_001_WAL.md) | ✅ Complete | Replaced BadgerDB with SQLite WAL in Go ingestion |
| 002 | TBD | ⏳ Pending | Parquet flush from SQLite |
| 003 | TBD | ⏳ Pending | Python backend Parquet indexer |
| 004 | TBD | ⏳ Pending | DataFusion query engine |
| 005 | TBD | ⏳ Pending | LanceDB vector search |
| 006 | TBD | ⏳ Pending | Query orchestrator (live + historical merge) |

## Current Focus

**001 - WAL Replacement** ✅: Replaced BadgerDB with SQLite WAL mode in the Go ingestion service using `crawshaw.io/sqlite` for optimal performance (30-50% less CPU overhead than pure-Go drivers).

## Architecture Overview (V4)

```
Client App → Go Ingestion (SQLite WAL) → Parquet Files → Python Backend (DuckDB metadata + DataFusion queries)
```

See [REFACTOR_V4_ARCHITECTURE.md](./REFACTOR_V4_ARCHITECTURE.md) for complete architecture details.
