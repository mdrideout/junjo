# ADR-001: Span Storage Architecture

**Status:** Accepted (Updated January 2026)
**Date:** 2025-12-10
**Author:** Matt

## Context

The Junjo AI Studio ingestion service receives OpenTelemetry spans at high throughput. We need a storage architecture that:

1. Provides low-latency queries for recent data (live dashboard updates)
2. Efficiently stores historical data for analysis
3. Minimizes memory usage during queries
4. Handles graceful restarts without data loss

## Decision

We implement a **two-tier storage architecture** using a Rust ingestion service with segmented Arrow IPC WAL:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    INGESTION ARCHITECTURE                            │
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

### Tier Definitions

| Tier | Storage | Location | Indexed | Lifecycle |
|------|---------|----------|---------|-----------|
| **HOT** | Segmented Arrow IPC | `wal/*.ipc` | N/A (source) | Until cold flush |
| **COLD** | Parquet | `parquet/year=*/month=*/day=*/` | Yes (SQLite metadata) | Permanent |

### Data Flow

1. **Ingestion**: Spans arrive via OTLP gRPC, written to in-memory buffer
2. **Segment Write**: When buffer reaches batch size (1000 spans), write IPC segment
3. **Reactive Flush**: Channel notifies flusher immediately when segment written
4. **Cold Flush**: Stream segments one-by-one to Parquet (constant memory)
5. **Hot Query**: Backend calls `PrepareHotSnapshot`, reads Parquet file directly

### Query Flow

Python backend queries both tiers via DataFusion:

1. **Register COLD**: Parquet files from SQLite metadata index (trace-level file mappings)
2. **Register HOT**: Parquet snapshot from `PrepareHotSnapshot` RPC
3. **Execute**: UNION ALL with deduplication (COLD > HOT priority)

The backend reads the hot snapshot file directly via DataFusion - no gRPC streaming needed.

## Configuration

### Ingestion Service (Rust)

| Setting | Default | Env Var | Description |
|---------|---------|---------|-------------|
| OTLP Port | 50051 | `GRPC_PORT` | Public gRPC port for OTLP ingestion |
| Internal Port | 50052 | `INTERNAL_GRPC_PORT` | Internal gRPC for backend queries |
| WAL Directory | `~/.junjo/spans/wal` | `WAL_DIR` | Arrow IPC WAL segments |
| Snapshot Path | `~/.junjo/spans/hot_snapshot.parquet` | `SNAPSHOT_PATH` | Hot snapshot file |
| Parquet Output | `~/.junjo/spans/parquet` | `PARQUET_OUTPUT_DIR` | Cold Parquet storage |
| Flush Size | 25MB | `FLUSH_MAX_MB` | WAL size to trigger flush |
| Flush Age | 1 hour | `FLUSH_MAX_AGE_SECS` | Max age before flush |
| Batch Size | 1000 | `BATCH_SIZE` | Spans per IPC segment |
| Backpressure | 250MB | `BACKPRESSURE_MAX_MB` | WAL size for backpressure |

## Consequences

### Benefits

1. **Constant memory**: Streaming flush processes one segment at a time
2. **Fast queries**: DataFusion handles both tiers efficiently
3. **No data loss**: Segmented WAL survives crashes
4. **Simple architecture**: Two tiers instead of three
5. **No gRPC streaming overhead**: Backend reads Parquet files directly

### Trade-offs

1. **Disk usage**: IPC segments until cold flush
2. **Query overhead**: Must merge two sources (mitigated by DataFusion efficiency)

### Failure Modes

| Scenario | Behavior |
|----------|----------|
| Crash before cold flush | Data safe in IPC segments, recovered on restart |
| gRPC unavailable | Query returns COLD only (graceful degradation) |
| Snapshot creation fails | Query returns COLD only |

## Implementation Files

### Rust Ingestion

- `ingestion/src/wal/arrow_wal.rs` - Segmented Arrow IPC WAL
- `ingestion/src/flusher/mod.rs` - Reactive flush logic
- `ingestion/src/server/trace_service.rs` - OTLP ingestion
- `ingestion/src/server/internal_service.rs` - PrepareHotSnapshot, FlushWAL
- `ingestion/src/config.rs` - Configuration

### Python Backend

- `backend/app/features/otel_spans/datafusion_query.py` - DataFusion queries
- `backend/app/features/otel_spans/repository.py` - Query orchestration
- `backend/app/features/span_ingestion/ingestion_client.py` - gRPC client
- `backend/app/db_sqlite/metadata/` - SQLite metadata index (trace→file mappings)

## References

- [DataFusion](https://datafusion.apache.org/) - SQL query engine
- [Arrow IPC](https://arrow.apache.org/docs/format/Columnar.html#ipc-streaming-format) - Efficient columnar data transfer
- [INGESTION.md](/INGESTION.md) - Detailed ingestion service documentation
