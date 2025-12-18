# Rust Ingestion Service Architecture

## Overview

Greenfield Rust ingestion service using **Segmented Arrow IPC as WAL** instead of SQLite. Optimized for minimal memory footprint and streaming flush to Parquet with constant memory usage.

**Architecture:**
```
OTLP Spans → Arrow batch → IPC segment (WAL) → Reactive flush to Parquet
                                      ↓
                              Backend reads hot_snapshot.parquet directly
```

## Library Versions (December 2025)

| Crate | Version | Purpose |
|-------|---------|---------|
| `arrow` | 57.2.0 | Arrow arrays, schemas, IPC |
| `parquet` | 57.2.0 | Parquet file writing |
| `tonic` | 0.14.2 | gRPC server/client |
| `prost` | 0.14.x | Protobuf serialization |
| `opentelemetry-proto` | 0.31.0 | OTLP type definitions |
| `tokio` | 1.x | Async runtime |
| `serde_json` | 1.x | JSON serialization for attributes |

## Service Structure

```
ingestion-rust/
├── Cargo.toml
├── build.rs                    # Proto compilation
├── proto/
│   ├── ingestion.proto         # Internal service (copy from /proto/)
│   └── opentelemetry/          # OTLP protos (via opentelemetry-proto crate)
├── src/
│   ├── main.rs                 # Entry point, dual server setup
│   ├── config.rs               # Environment configuration
│   ├── wal/
│   │   ├── mod.rs
│   │   ├── arrow_wal.rs        # Arrow IPC WAL core
│   │   ├── schema.rs           # Span Arrow schema
│   │   └── span_record.rs      # OTLP → SpanRecord conversion
│   ├── server/
│   │   ├── mod.rs
│   │   ├── trace_service.rs    # Public: OTLP TraceService
│   │   ├── internal_service.rs # Internal: PrepareHotSnapshot, FlushWAL
│   │   ├── auth.rs             # API key interceptor
│   │   └── backpressure.rs     # Memory-based backpressure
│   ├── flusher/
│   │   ├── mod.rs              # Flush orchestration
│   │   └── parquet.rs          # IPC → Parquet writer
│   └── backend/
│       └── client.rs           # Backend notification client
└── Dockerfile
```

## API Surface

### Public gRPC (port 50051)

**TraceService** (OTLP standard):
- `Export(ExportTraceServiceRequest) → ExportTraceServiceResponse`
- API key authentication via `x-junjo-api-key` header
- Backpressure returns `ResourceExhausted` when WAL size exceeds threshold

### Internal gRPC (port 50052)

**InternalIngestionService**:

| RPC | Purpose |
|-----|---------|
| `PrepareHotSnapshot` | Create stable Parquet snapshot; backend reads file directly via DataFusion |
| `FlushWAL` | Trigger immediate flush to cold Parquet storage |

The internal API is intentionally minimal. The backend reads hot data by:
1. Calling `PrepareHotSnapshot` to get a stable Parquet file
2. Reading that file directly via DataFusion (no gRPC streaming)

This decoupled approach is simpler and more performant than streaming Arrow IPC over gRPC.

### Proto Definition

```protobuf
service InternalIngestionService {
  // Backend triggers snapshot, then reads Parquet file directly via DataFusion
  rpc PrepareHotSnapshot(PrepareHotSnapshotRequest) returns (PrepareHotSnapshotResponse) {}

  // Trigger immediate flush of WAL segments to cold Parquet storage
  rpc FlushWAL(FlushWALRequest) returns (FlushWALResponse) {}
}

message PrepareHotSnapshotRequest {}
message PrepareHotSnapshotResponse {
  string snapshot_path = 1;   // Path to stable Parquet file
  int64 row_count = 2;        // Number of spans in snapshot
  int64 file_size_bytes = 3;  // File size for logging
  bool success = 4;
  string error_message = 5;
}

message FlushWALRequest {}
message FlushWALResponse {
  bool success = 1;
  string error_message = 2;
}
```

## Arrow Schema

| Field | Arrow Type | Notes |
|-------|------------|-------|
| span_id | Utf8 | Hex-encoded |
| trace_id | Utf8 | Hex-encoded |
| parent_span_id | Utf8 (nullable) | |
| service_name | Utf8 | |
| name | Utf8 | |
| span_kind | Int8 | |
| start_time | Timestamp(ns, UTC) | |
| end_time | Timestamp(ns, UTC) | |
| duration_ns | Int64 | |
| status_code | Int8 | |
| status_message | Utf8 (nullable) | |
| attributes | Utf8 | JSON string |
| events | Utf8 | JSON string |
| resource_attributes | Utf8 | JSON string |

## Data Flow

### Segmented WAL Architecture

The WAL uses a **segmented log pattern** where each batch creates a separate IPC file:

```
wal/
  batch_1734482100000000001.ipc  (~1-2MB each)
  batch_1734482103000000002.ipc
  batch_1734482106000000003.ipc
  ...
```

**Benefits:**
- Constant memory during reads (process one segment at a time)
- Streaming flush (read segment → write to parquet → drop → next)
- Atomic writes (temp file → rename)
- Safe concurrent access (flusher never sees incomplete segments)

### Write Path

1. OTLP span received via `TraceService.Export`
2. Convert to `SpanRecord` struct (one-time allocation)
3. Append to in-memory pending buffer
4. When buffer reaches `BATCH_SIZE` spans:
   - Build Arrow `RecordBatch`
   - Write to `.ipc.tmp` file, then atomic rename to `.ipc`
   - **Notify flusher via channel** (reactive flush trigger)
5. Timer-based flush every 3s for durability (partial batches)

### Reactive Flush

Flush is triggered **reactively** rather than purely by polling:

```
gRPC Request → TraceService → WAL.write_spans()
                                    ↓ segment written
                              segment_tx.send(())
                                    ↓
Flusher.run() ←─────────────────────┘
    │
    ├── Reactive: segment notification → check_and_flush() immediately
    ├── Durability: every 3s → flush pending spans to IPC
    └── Fallback: every 10s → check age threshold for stale data
```

This ensures flush triggers immediately when the size threshold is crossed, preventing WAL overshoot.

### Hot Snapshot Path

1. Backend calls `PrepareHotSnapshot`
2. Ingestion flushes pending in-memory spans to a segment
3. Ingestion streams all WAL segments to a stable Parquet snapshot file
4. Ingestion returns snapshot file path
5. Backend reads Parquet file directly via DataFusion

### Cold Flush Path

1. Triggered by byte threshold (reactive) or age threshold (periodic) or manual `FlushWAL`
2. **Stream** segments one at a time (constant memory):
   - Read segment via `StreamReader`
   - Write batches to Parquet via `ArrowWriter`
   - Drop segment data before reading next
3. Atomic rename: `.parquet.tmp` → `.parquet`
4. Notify backend via `NotifyNewParquetFile`
5. Delete only the segments that were flushed (preserves new arrivals)

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GRPC_PORT` | 50051 | Public gRPC port (OTLP ingestion) |
| `INTERNAL_GRPC_PORT` | 50052 | Internal gRPC port (backend queries) |
| `WAL_DIR` | `~/.junjo/spans/wal` | Directory for Arrow IPC WAL segments |
| `SNAPSHOT_PATH` | `~/.junjo/spans/hot_snapshot.parquet` | Hot snapshot file for backend reads |
| `PARQUET_OUTPUT_DIR` | `~/.junjo/spans/parquet` | Cold Parquet output directory |
| `FLUSH_MAX_MB` | 25 | WAL size threshold to trigger flush (MB) |
| `FLUSH_MAX_AGE_SECS` | 3600 | Max age before flush (1 hour) |
| `BATCH_SIZE` | 1000 | Spans per IPC segment |
| `BACKPRESSURE_MAX_MB` | 250 | WAL size threshold for backpressure |
| `BACKEND_GRPC_HOST` | localhost | Backend gRPC host for notifications |
| `BACKEND_GRPC_PORT` | 50053 | Backend gRPC port |
| `JUNJO_LOG_LEVEL` | info | Log level (debug, info, warn, error) |

### Internal Timers (Not Configurable)

| Timer | Interval | Purpose |
|-------|----------|---------|
| Pending flush | 3s | Flush partial batches to IPC for durability |
| Age check | 10s | Fallback check for age-based flush |
| Segment notification | immediate | Reactive flush when segment written |
