# ADR-001: Three-Tier Span Storage Architecture

**Status:** Accepted
**Date:** 2025-12-10
**Author:** Matt

## Context

The Junjo AI Studio ingestion service receives OpenTelemetry spans at high throughput. We need a storage architecture that:

1. Provides low-latency queries for recent data (live dashboard updates)
2. Efficiently stores historical data for analysis
3. Minimizes memory usage during queries
4. Handles graceful restarts without data loss

Previously, all span data lived in SQLite until a cold flush to Parquet. This meant queries had to merge potentially large SQLite result sets with Parquet files, causing memory pressure.

## Decision

We implement a **three-tier storage architecture**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         QUERY FLOW                                   │
│                                                                      │
│   Python Backend (DataFusion)                                        │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │  SELECT * FROM (                                              │  │
│   │    SELECT *, 1 as priority FROM cold_spans                    │  │
│   │    UNION ALL                                                  │  │
│   │    SELECT *, 2 as priority FROM warm_spans                    │  │
│   │    UNION ALL                                                  │  │
│   │    SELECT *, 3 as priority FROM hot_spans                     │  │
│   │  ) deduplicated by span_id (lowest priority wins)             │  │
│   └──────────────────────────────────────────────────────────────┘  │
│              │                    │                    │             │
│              ▼                    ▼                    ▼             │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│   │  COLD TIER   │    │  WARM TIER   │    │      HOT TIER        │  │
│   │  (Parquet)   │    │  (Parquet)   │    │   (Arrow IPC)        │  │
│   │              │    │              │    │                      │  │
│   │  Indexed in  │    │  Globbed     │    │  gRPC streaming      │  │
│   │  DuckDB      │    │  from tmp/   │    │  from Ingestion      │  │
│   └──────────────┘    └──────────────┘    └──────────────────────┘  │
│         ▲                    ▲                       ▲               │
└─────────│────────────────────│───────────────────────│───────────────┘
          │                    │                       │
┌─────────│────────────────────│───────────────────────│───────────────┐
│         │          INGESTION SERVICE (Go)            │               │
│         │                    │                       │               │
│   ┌─────┴──────┐      ┌──────┴─────┐          ┌──────┴─────┐        │
│   │ Cold Flush │      │Warm Snapshot│          │  SQLite    │        │
│   │            │      │            │          │    WAL     │        │
│   │ Triggers:  │      │ Triggers:  │          │            │        │
│   │ - 100K rows│      │ - 1MB data │          │ All spans  │        │
│   │ - 1hr age  │      │   (every   │          │ inserted   │        │
│   │ - shutdown │      │    15s)    │          │ here first │        │
│   └────────────┘      └────────────┘          └────────────┘        │
│         │                    │                       ▲               │
│         │                    │                       │               │
│         │   Deletes from     │   Copies to tmp/      │  OTLP gRPC   │
│         │   SQLite + cleans  │   (no delete)         │  ingest      │
│         │   warm files       │                       │               │
│         ▼                    ▼                       │               │
│   ┌────────────────────────────────────────┐        │               │
│   │        parquet/                         │        │               │
│   │        ├── year=2025/month=12/day=10/  │ (cold) │               │
│   │        │   └── *.parquet               │        │               │
│   │        └── tmp/                        │ (warm) │               │
│   │            └── warm_*.parquet          │        │               │
│   └────────────────────────────────────────┘        │               │
└─────────────────────────────────────────────────────────────────────┘
```

### Tier Definitions

| Tier | Storage | Location | Indexed | Lifecycle |
|------|---------|----------|---------|-----------|
| **HOT** | SQLite WAL | `sqlite/wal.db` | N/A (source) | Until cold flush |
| **WARM** | Parquet | `parquet/tmp/warm_*.parquet` | No (globbed) | Cleaned on cold flush |
| **COLD** | Parquet | `parquet/year=*/month=*/day=*/` | Yes (DuckDB) | Permanent |

### Data Flow

1. **Ingestion**: Spans arrive via OTLP gRPC and are inserted into SQLite WAL
2. **Warm Snapshot** (every 15s if threshold met):
   - Check bytes since last warm snapshot
   - If >= 1MB threshold, write spans to `tmp/warm_*.parquet`
   - Update cursor (do NOT delete from SQLite)
3. **Cold Flush** (on row count, age, or shutdown):
   - Write ALL SQLite spans to date-partitioned Parquet
   - Delete spans from SQLite
   - Clean up warm files in `tmp/`
   - Index new Parquet file in DuckDB metadata

### Query Flow

Python backend queries all three tiers via DataFusion:

1. **Register COLD**: Parquet files from DuckDB metadata index
2. **Register WARM**: Glob `parquet/tmp/warm_*.parquet`
3. **Register HOT**: Arrow IPC from gRPC `GetHotSpansArrow(since_warm_ulid=...)`
4. **Execute**: UNION ALL with deduplication (COLD > WARM > HOT priority)

The `since_warm_ulid` parameter ensures HOT tier only returns spans newer than the last warm snapshot, avoiding duplicates.

## Configuration

### Ingestion Service (Go)

| Setting | Default | Env Var | Description |
|---------|---------|---------|-------------|
| Flush Interval | 15s | `FLUSH_INTERVAL` | How often to check flush conditions |
| Warm Threshold | 10MB | `WARM_SNAPSHOT_BYTES` | Bytes before warm snapshot triggers |
| Cold Max Rows | 100,000 | `FLUSH_MAX_ROWS` | Row count to trigger cold flush |
| Cold Max Age | 1 hour | `FLUSH_MAX_AGE` | Time since last flush to trigger |
| Cold Min Rows | 1,000 | `FLUSH_MIN_ROWS` | Minimum rows for age-based flush |

### Python Backend

| Setting | Default | Description |
|---------|---------|-------------|
| gRPC Max Message | 100MB | Max Arrow IPC payload size |

## Consequences

### Benefits

1. **Reduced memory pressure**: HOT tier only contains data since last warm snapshot (~1MB max under normal load)
2. **Fast queries**: DataFusion handles all three tiers efficiently
3. **No data loss**: Graceful shutdown flushes all SQLite data to cold Parquet
4. **Incremental snapshots**: Warm tier prevents large HOT tier accumulation

### Trade-offs

1. **Complexity**: Three tiers vs two requires more coordination
2. **Disk usage**: Warm tier temporarily duplicates data (SQLite + Parquet)
3. **Query overhead**: Must merge three sources (mitigated by DataFusion efficiency)

### Failure Modes

| Scenario | Behavior |
|----------|----------|
| Crash before warm snapshot | Data safe in SQLite, HOT tier larger on restart |
| Crash after warm, before cold | Warm files + SQLite both have data; dedup handles it |
| gRPC unavailable | Query returns COLD + WARM only (graceful degradation) |
| Warm cursor stale | Full WAL query (no `since_warm_ulid` filter) |

## Implementation Files

- `ingestion/storage/flusher.go` - Cold flush logic
- `ingestion/storage/warm_flusher.go` - Warm snapshot logic
- `ingestion/config/config.go` - Configuration defaults
- `backend/app/db_duckdb/unified_query.py` - Three-tier DataFusion queries
- `backend/app/features/otel_spans/repository.py` - Query orchestration
- `backend/app/features/span_ingestion/ingestion_client.py` - gRPC client for HOT tier

## References

- [DataFusion](https://datafusion.apache.org/) - SQL query engine
- [Arrow IPC](https://arrow.apache.org/docs/format/Columnar.html#ipc-streaming-format) - Efficient columnar data transfer
