# ADR-001: Segmented WAL Architecture

## Status

Accepted

## Context

The ingestion service receives OTLP spans on the public gRPC path and must make them durable before they are eventually queried through the backend.

The end-state system has to satisfy all of these at once:

- keep OTLP write latency low
- survive process crashes without losing accepted batches
- avoid blocking new writes while cold files are being produced
- support backend reads of unflushed data
- stay within a small-host memory budget

A single append-only WAL file is the wrong shape for those requirements because read-heavy work and write-heavy work contend on the same artifact:

- cold flush needs to read historical buffered data and turn it into Parquet
- hot reads need a stable snapshot the backend can open directly
- OTLP ingestion needs to keep accepting new writes while those read operations are happening

The strategic requirement is not just "buffer before Parquet." It is "use one durable intermediate representation that can serve both background cold flush and on-demand hot reads without turning either path into a streaming RPC problem."

## Decision

Use a segmented Arrow IPC write-ahead log.

### End-State Architecture

The durable flow is:

1. OTLP ingestion converts spans into records and appends them to an in-memory pending batch.
2. Completed batches are written as new Arrow IPC WAL segment files.
3. Background cold flush snapshots the currently completed segments, streams them into Parquet, and deletes only the segments it flushed.
4. On-demand hot snapshot creation uses the same segment set to build a stable Parquet file for backend queries.
5. The backend reads Parquet files directly rather than receiving span payloads over gRPC.

That gives the system one durable source of truth between ingest and queryable Parquet, while keeping backend query transport simple.

### Why Segmented Instead Of Single-File WAL

Segmenting the WAL is part of the architectural decision, not an implementation detail.

Problem with a single append-only WAL file:

- readers and writers contend on the same file
- cold flush and hot snapshot creation would either block new writes or require more complex file swapping
- large flushes would turn into longer write stalls

Segmented WAL strategy:

- each completed batch becomes its own immutable segment
- readers operate on a snapshot of completed segments
- writers keep producing new segments while older ones are being flushed
- crash recovery is "recover whatever complete segments remain"

### Why Arrow IPC

Arrow IPC is the durable intermediate format because it fits the end state:

- fast to write in batches
- efficient to stream back into Arrow/Parquet
- usable as the shared source for both cold flush and hot snapshot creation

The strategic contract is "segments are durable, batch-shaped, and re-readable," not "the backend ever reads IPC directly."

### Hot Snapshot Strategy

The backend does not fetch spans over gRPC.

Instead:

- ingestion creates a stable Parquet snapshot on demand
- backend receives a file path plus query context
- backend reads the file directly with DataFusion alongside cold Parquet files

This keeps the internal RPC surface small and avoids inventing a second transport/query protocol for recent data.

### Operational Invariants

These are part of the decision:

- completed segments must appear atomically so readers never consume partial files
- cold flush must operate on a snapshot of completed segments, not the live mutable write target
- hot snapshot creation must produce a stable file the backend can open safely
- memory usage must scale with batch size and streaming behavior, not with total WAL size
- deleting flushed segments must not race with newly written segments

Implementation defaults and tunables are not owned by this ADR. They live in code, especially `ingestion/src/config.rs`.

## Strategic Lessons Locked Into The End State

These are not transient implementation notes. They explain why the current shape exists.

### Timer-Based Durability Flush Must Stay Off The Hot Path

Timer-based "flush pending to IPC" work should be background-driven rather than checked on every write.

Why:

- per-request timer checks on the write path can collapse batching after idle periods
- collapsed batching creates too many tiny segments
- too many tiny segments increases lock hold time and file I/O churn

The end-state strategy is:

- batch-threshold flushes may happen while handling writes
- timer-based durability flushes happen in the flusher background loop

### Backpressure Monitoring Must Stay Off The Hot Path

The system uses RSS-based backpressure, but request handlers should not do heavyweight process-memory syscalls on every request.

The end-state strategy is:

- a background monitor computes pressure state periodically
- the OTLP path reads a cheap shared flag
- rejection under pressure is fast and predictable

### Allocator Choice Matters Because Backpressure Uses Process Memory

Allocator behavior affects operational correctness when backpressure is based on process memory rather than only logical in-process buffers.

The end-state system uses `mimalloc` so memory can return to the OS more predictably without the severe throughput penalty previously seen with more aggressive allocator behavior.

This ADR does not freeze allocator benchmarks or tuning values, but it does record the architectural reason allocator choice matters here.

## Alternatives Considered

### Single WAL File

Rejected because it couples writers, flush readers, and hot-read preparation to the same artifact and makes non-blocking behavior harder.

### Direct Parquet Writes

Rejected because it pushes more work and latency into the ingest path and weakens the buffering layer between acceptance and cold storage.

### Streaming Hot Reads Over gRPC

Rejected because it would create a second query transport path when the backend already reads Parquet with DataFusion.

## Consequences

### Positive

- New writes can continue while older segments are being flushed.
- Crash recovery is straightforward: recover from complete remaining segments.
- Cold flush and hot snapshot creation share the same durable source.
- Backend query integration stays simple because hot data is exposed as a file, not a stream protocol.
- Memory pressure is bounded by batching and streaming rather than total retained WAL history.

### Negative

- The system manages more files than a single-log design.
- Atomic segment finalization and reader filtering are mandatory for correctness.
- The architecture depends on careful coordination between WAL, flusher, hot snapshot, and backend query registration.

## Source Of Truth

The active implementation lives in:

- `ingestion/src/wal/`
- `ingestion/src/flusher/`
- `ingestion/src/server/trace_service.rs`
- `ingestion/src/server/internal_service.rs`
- `ingestion/src/server/backpressure.rs`
- `ingestion/src/main.rs`
- `ingestion/src/config.rs`

## Related

- `ingestion/adr/002-sqlite-metadata-index.md`
- `proto/ingestion.proto`
