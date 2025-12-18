# ADR-001: Span Storage Architecture

**Status:** Accepted (Updated December 2025)
**Date:** 2025-12-10
**Author:** Matt

## Context

The Junjo AI Studio ingestion service receives OpenTelemetry spans at high throughput. We need a storage architecture that:

1. Provides low-latency queries for recent data (live dashboard updates)
2. Efficiently stores historical data for analysis
3. Minimizes memory usage during queries
4. Handles graceful restarts without data loss

Previously, all span data lived in SQLite until a cold flush to Parquet. This meant queries had to merge potentially large SQLite result sets with Parquet files, causing memory pressure.

**Update (December 2025):** The Rust ingestion service uses a simplified two-tier architecture with a segmented Arrow IPC WAL. See the "Rust Implementation" section below.

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

## Rust Implementation (Two-Tier)

The Rust ingestion service (`ingestion-rust/`) uses a simplified **two-tier architecture** without a separate WARM tier:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RUST INGESTION ARCHITECTURE                       │
│                                                                      │
│   Python Backend (DataFusion)                                        │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │  SELECT * FROM (                                              │  │
│   │    SELECT * FROM cold_spans    -- date-partitioned Parquet   │  │
│   │    UNION ALL                                                  │  │
│   │    SELECT * FROM hot_snapshot  -- on-demand Parquet snapshot │  │
│   │  ) deduplicated by span_id                                    │  │
│   └──────────────────────────────────────────────────────────────┘  │
│              │                                      │                │
│              ▼                                      ▼                │
│   ┌──────────────────────┐            ┌─────────────────────────┐   │
│   │     COLD TIER        │            │       HOT TIER          │   │
│   │   (Parquet files)    │            │  (Segmented IPC WAL)    │   │
│   │                      │            │                         │   │
│   │  parquet/            │            │  wal/                   │   │
│   │   year=2025/         │            │   batch_*.ipc           │   │
│   │    month=12/         │            │                         │   │
│   │     day=18/*.parquet │            │  hot_snapshot.parquet   │   │
│   └──────────────────────┘            └─────────────────────────┘   │
│              ▲                                      ▲                │
└──────────────│──────────────────────────────────────│────────────────┘
               │                                      │
┌──────────────│──────────────────────────────────────│────────────────┐
│              │        INGESTION SERVICE (Rust)      │                │
│              │                                      │                │
│   ┌──────────┴───────┐                 ┌────────────┴────────┐      │
│   │  Cold Flush      │                 │ PrepareHotSnapshot  │      │
│   │                  │                 │                     │      │
│   │  Triggers:       │                 │ On-demand:          │      │
│   │  - 25MB WAL size │◄── reactive ───│ Backend calls RPC,  │      │
│   │  - 1hr age       │    channel     │ reads file directly │      │
│   │  - shutdown      │                 │                     │      │
│   └──────────────────┘                 └─────────────────────┘      │
│              ▲                                      ▲                │
│              │ streaming flush                      │ OTLP gRPC     │
│              │ (constant memory)                    │ ingest        │
│   ┌──────────┴──────────────────────────────────────┴────────┐      │
│   │              Segmented Arrow IPC WAL                      │      │
│   │                                                           │      │
│   │  wal/                                                     │      │
│   │   batch_1734482100000000001.ipc  (~1-2MB each)           │      │
│   │   batch_1734482103000000002.ipc                          │      │
│   │   ...                                                     │      │
│   └───────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────┘
```

### Key Differences from Go Implementation

| Aspect | Go (Three-Tier) | Rust (Two-Tier) |
|--------|-----------------|-----------------|
| HOT storage | SQLite WAL | Segmented Arrow IPC |
| WARM tier | Periodic snapshots | None (on-demand only) |
| Hot data access | gRPC streaming | Backend reads file directly |
| Flush trigger | Polling (10s) | Reactive (channel notification) |
| Memory usage | Loads all SQLite data | Constant (streams one segment at a time) |

### Rust Data Flow

1. **Ingestion**: Spans arrive via OTLP gRPC, written to in-memory buffer
2. **Segment Write**: When buffer reaches batch size (1000 spans), write IPC segment
3. **Reactive Flush**: Channel notifies flusher immediately when segment written
4. **Cold Flush**: Stream segments one-by-one to Parquet (constant memory)
5. **Hot Query**: Backend calls `PrepareHotSnapshot`, reads Parquet file directly

### Why Two Tiers?

The WARM tier was designed to reduce HOT tier size for gRPC streaming. With the Rust implementation:
- Backend reads a Parquet file directly (no streaming overhead)
- Segmented WAL allows constant-memory snapshot creation
- Reactive flush prevents WAL from growing too large

The WARM tier's complexity is no longer needed.

## Implementation Files

### Rust Ingestion (Primary)

- `ingestion-rust/src/wal/arrow_wal.rs` - Segmented Arrow IPC WAL
- `ingestion-rust/src/flusher/mod.rs` - Reactive flush logic
- `ingestion-rust/src/server/trace_service.rs` - OTLP ingestion
- `ingestion-rust/src/server/internal_service.rs` - PrepareHotSnapshot, FlushWAL
- `ingestion-rust/src/config.rs` - Configuration

### Go Ingestion (Legacy)

- `ingestion/storage/flusher.go` - Cold flush logic
- `ingestion/storage/repository.go` - SQLite WAL operations
- `ingestion/config/config.go` - Configuration defaults

### Python Backend

- `backend/app/db_duckdb/unified_query.py` - DataFusion queries
- `backend/app/features/otel_spans/repository.py` - Query orchestration
- `backend/app/features/span_ingestion/ingestion_client.py` - gRPC client

## References

- [DataFusion](https://datafusion.apache.org/) - SQL query engine
- [Arrow IPC](https://arrow.apache.org/docs/format/Columnar.html#ipc-streaming-format) - Efficient columnar data transfer
- [INGESTION_RUST.md](/INGESTION_RUST.md) - Rust ingestion service details
