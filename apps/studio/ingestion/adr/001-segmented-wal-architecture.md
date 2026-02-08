# ADR-001: Segmented Write-Ahead Log Architecture

## Status
Accepted

## Context

The ingestion service receives OpenTelemetry spans via gRPC and must durably store them before flushing to Parquet files. Key requirements:

1. **Durability**: Spans must survive process crashes
2. **Low latency**: gRPC responses should be fast
3. **Non-blocking flush**: Writing new spans should not block during cold flush
4. **Bounded memory**: Memory usage should not grow unbounded

## Decision

Use a **segmented write-ahead log** with Arrow IPC format.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WRITE PATH                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  gRPC Request (spans)                                                       │
│        │                                                                    │
│        ▼                                                                    │
│  ┌──────────────┐                                                           │
│  │ pending      │  In-memory buffer (up to 1000 spans)                      │
│  │ Vec<Span>    │                                                           │
│  └──────┬───────┘                                                           │
│         │                                                                   │
│         │  Trigger: 1000 spans OR 3 seconds                                 │
│         ▼                                                                   │
│  ┌──────────────┐                                                           │
│  │ StreamWriter │  Write batch to NEW segment file                          │
│  └──────┬───────┘                                                           │
│         │                                                                   │
│         ▼                                                                   │
│  wal/                                                                       │
│    seg_0001_1734567890.ipc  (1-2MB)                                         │
│    seg_0002_1734567893.ipc  (1-2MB)                                         │
│    seg_0003_1734567896.ipc  (1-2MB)                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    COLD FLUSH (Background, Non-blocking)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Trigger: total_size ≥ 25MB OR age ≥ 1 hour (checked every 10s)             │
│                                                                             │
│  1. Flush pending buffer → create final segment                             │
│  2. SNAPSHOT: List all .ipc segments                                        │
│     (New segments can be created during flush)                              │
│  3. STREAM: Read each segment → write to Parquet                            │
│     Memory: O(batch), not O(total_size)                                     │
│  4. DELETE: Remove only the flushed segments                                │
│  5. RECORD: Track flushed Parquet path (in-memory, bounded)                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                      HOT SNAPSHOT (On-demand RPC)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PrepareHotSnapshot() called by backend                                     │
│                                                                             │
│  1. Flush pending buffer → create segment                                   │
│  2. SNAPSHOT: List all .ipc segments                                        │
│  3. STREAM: Read segments → write to temp Parquet                           │
│  4. RENAME: Atomic rename to hot_snapshot.parquet                           │
│  5. RETURN: snapshot_path + recent_cold_paths                               │
│     (backend reads files directly via DataFusion)                           │
│                                                                             │
│  NOTE: Does NOT delete segments (cold flush handles deletion)               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Segmented vs Single File?

**Problem with single IPC file:**
- Cannot read and write simultaneously
- During flush (reading), new spans would be blocked
- Flush can take 1-4 seconds

**Segmented solution:**
- Each batch creates a NEW segment file
- Writer and flusher operate on different files
- New segments accumulate while old segments are being flushed

### Atomic Segment Completion

**Problem:** Flusher might read a segment while writer is still writing it.

**Solution:** Atomic file rename

```
Writer flow:
1. Write to seg_XXX.ipc.tmp
2. Call writer.finish() (closes file)
3. Atomic rename: seg_XXX.ipc.tmp → seg_XXX.ipc

Flusher flow:
1. list_segments() only returns *.ipc files
2. .ipc.tmp files are invisible to flusher
3. All .ipc files are guaranteed complete
```

### Memory Profile

| Phase | Memory Usage |
|-------|--------------|
| Buffering spans | ~3MB (1000 spans) |
| Writing segment | ~3MB (batch to Arrow) |
| Flushing | ~3MB per batch (streaming) |

Total memory is O(batch_size), not O(file_size).

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `BATCH_SIZE` | 1000 | Spans per segment |
| `FLUSH_MAX_MB` | 25 | Total WAL size before cold flush |
| `FLUSH_MAX_AGE_SECS` | 3600 | Max age before cold flush |

## Consequences

### Positive
- Non-blocking writes during flush
- Bounded memory usage
- Simple crash recovery (just read all .ipc files)
- Streaming flush prevents memory spikes

### Negative
- More files to manage than single-file approach
- Need to handle atomic rename for safety
- Directory listing on each flush

### Alternatives Considered

1. **Single IPC file with double buffering**: More complex, requires file swapping
2. **Single IPC file with write blocking**: Simpler but blocks during flush
3. **Direct Parquet writes**: Higher latency, no buffering

## Performance Lessons Learned

### Timer-Based Flush Must Be Background Only

**Problem:** Original implementation checked timer on every `write_span()`:
```rust
// BAD: Every span checks timer, causing excessive flushes
let should_flush = pending.len() >= batch_size
    || (last_flush.elapsed() >= 3s && !pending.is_empty());
```

After 3+ seconds of idle time, the first span triggers a flush of 1 span. With high concurrency (50 requests × 70 spans), this caused:
- 70 IPC files per request instead of batched writes
- 1.3+ second lock contention waiting for file I/O
- ~15 workflows/sec instead of ~300/sec

**Solution:** Timer check moved to background flusher task:
```rust
// write_span() - only batch threshold
if pending.len() >= batch_size { flush_pending(); }

// flusher background task - timer check every 3s
if wal.needs_timer_flush() { wal.flush_pending(); }
```

### Memory Allocator Selection

**Problem:** Default Rust allocator pools freed memory and never returns it to OS, causing RSS to grow to 550MB+ even when actual usage is lower. This triggers backpressure based on RSS measurement.

**Attempted Solutions:**
1. **jemalloc**: Returns memory to OS but caused 20x slowdown due to aggressive memory return causing allocation thrashing
2. **mimalloc**: Returns memory to OS with better performance characteristics

**Current Choice:** mimalloc - balances memory return to OS (for container coexistence) with performance.

### Backpressure Monitoring Must Be Background

**Problem:** Original backpressure check called sysinfo syscalls on every gRPC request:
```rust
// BAD: Expensive syscalls on hot path
fn check(&self) -> bool {
    let mut sys = System::new();
    sys.refresh_memory();
    sys.refresh_processes(...);
    // ...
}
```

**Solution:** Background task updates AtomicBool every 500ms:
```rust
// Background task
loop {
    let is_under_pressure = check_memory();
    pressure_flag.store(is_under_pressure, Ordering::Relaxed);
    sleep(500ms).await;
}

// Hot path - just reads AtomicBool
fn is_under_pressure(&self) -> bool {
    self.under_pressure.load(Ordering::Relaxed)
}
```

## Related

- Arrow IPC format: https://arrow.apache.org/docs/format/Columnar.html#ipc-streaming-format
- Parquet format: https://parquet.apache.org/docs/
