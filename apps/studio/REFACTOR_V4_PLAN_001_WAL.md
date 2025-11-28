# 001: SQLite WAL Replacement

Replace BadgerDB with SQLite WAL mode in the Go ingestion service.

## Goal

Swap the storage backend from BadgerDB to SQLite while maintaining:
- Same gRPC API contract (no proto changes)
- Same behavior (monotonic ULID keys, unretrieved count tracking)
- Same interface to callers (`WriteSpan`, `ReadSpans`, etc.)

## Why SQLite?

From [REFACTOR_V4_ARCHITECTURE.md](./REFACTOR_V4_ARCHITECTURE.md#decision-1-sqlite-for-live-span-buffer):

| Aspect | BadgerDB | SQLite WAL |
|--------|----------|------------|
| Query capability | Manual key-prefix indexes | Full SQL, automatic indexes |
| Memory behavior | Unpredictable (2GB+ reported) | Predictable (~5-20MB) |
| Write throughput | ~500K/sec | ~100K/sec (sufficient) |
| Index maintenance | Manual | Automatic |
| Crash recovery | LSM compaction | WAL replay |

## Files to Change

### Create New
- `ingestion/storage/sqlite.go` - SQLite storage implementation
- `ingestion/storage/sqlite_test.go` - Unit tests

### Modify
- `ingestion/main.go` - Initialize SQLite instead of BadgerDB
- `ingestion/Dockerfile` - Remove BadgerDB, add SQLite dependencies (if needed)
- `ingestion/go.mod` - Add `modernc.org/sqlite` or `mattn/go-sqlite3`

### Delete (after validation)
- `ingestion/storage/badger.go`
- `ingestion/storage/badger_test.go`

### Unchanged
- `ingestion/storage/span_data.go` - Serialization logic stays the same
- `ingestion/server/otel_trace_service.go` - Calls `WriteSpan`, interface unchanged
- `ingestion/server/wal_reader_service.go` - Calls `ReadSpans`, interface unchanged
- `proto/ingestion.proto` - API contract unchanged
- `proto/span_data_container.proto` - Storage format unchanged

## SQLite Schema

```sql
-- Spans table with ULID primary key for monotonic ordering
CREATE TABLE IF NOT EXISTS spans (
    key_ulid BLOB PRIMARY KEY,      -- 16-byte ULID
    span_bytes BLOB NOT NULL,       -- Serialized span proto
    resource_bytes BLOB NOT NULL    -- Serialized resource proto
) WITHOUT ROWID;

-- Metadata for counters and state
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

-- Initialize counter
INSERT OR IGNORE INTO metadata (key, value) VALUES ('unretrieved_count', 0);
```

**Notes:**
- `WITHOUT ROWID` optimization since we use BLOB primary key
- ULID keys are 16 bytes, stored as BLOB for efficient comparison
- Same `span_bytes` + `resource_bytes` structure as current `SpanDataContainer`

## Storage Interface

The new `sqlite.go` must implement the same interface as `badger.go`:

```go
type Storage struct {
    db         *sql.DB
    ulidGen    *MonotonicULIDGenerator
    reconciler *time.Ticker
}

// Core operations (same signatures as BadgerDB)
func NewStorage(dbPath string) (*Storage, error)
func (s *Storage) Close() error
func (s *Storage) WriteSpan(span *tracepb.Span, resource *resourcepb.Resource) error
func (s *Storage) ReadSpans(startKey []byte, batchSize int, sendFunc SendSpanFunc) ([]byte, int, error)

// Counter operations
func (s *Storage) GetUnretrievedCount() (uint64, error)
func (s *Storage) DecrementAndGetCount(decrement uint64) (uint64, error)
func (s *Storage) ReconcileCount() error
```

## Implementation Steps

### Step 1: Add SQLite Dependency

```bash
cd ingestion
go get crawshaw.io/sqlite
```

Using `crawshaw.io/sqlite` for:
- **Lower CPU overhead** (~30-50% vs pure-Go) - critical for sustained ingestion on resource-constrained VMs
- **Predictable memory** - SQLite's C allocator handles hot path, Go GC only sees edges
- **Low-level API access** - `sqlite3_blob` for zero-copy reads, WAL checkpoint control, `sqlite3_snapshot` for consistent reads during flush
- **Best concurrent performance** among CGO options

Tradeoff: Requires CGO and SQLite C library in Dockerfile (already have gcc from protoc build stage).

### Step 2: Create sqlite.go

Implement `Storage` struct with:

1. **Database initialization**
   - Open SQLite with WAL mode: `PRAGMA journal_mode=WAL`
   - Set busy timeout: `PRAGMA busy_timeout=5000`
   - Create tables if not exist

2. **WriteSpan**
   - Generate monotonic ULID
   - Marshal span/resource to bytes (reuse `span_data.go`)
   - INSERT with counter increment in single transaction

3. **ReadSpans**
   - SELECT with `key_ulid > ?` ORDER BY `key_ulid` LIMIT `batchSize`
   - Stream results via `sendFunc` callback
   - Track last key for pagination
   - Handle corrupted spans (log warning, continue)

4. **Counter operations**
   - `GetUnretrievedCount`: SELECT from metadata table
   - `DecrementAndGetCount`: UPDATE with floor at 0
   - `ReconcileCount`: COUNT(*) from spans table, update metadata

### Step 3: Create sqlite_test.go

Port tests from `badger_test.go`:
- `TestWriteAndReadSpan`
- `TestReadSpansEmpty`
- `TestReadSpansPagination`
- `TestMonotonicULIDOrdering`
- `TestCounterOperations`
- `TestReconcileCount`
- `TestConcurrentWrites`

### Step 4: Update main.go

Replace BadgerDB storage initialization with SQLite. Change environment variable from `JUNJO_BADGERDB_PATH` to `JUNJO_WAL_SQLITE_PATH`.

### Step 5: Update Dockerfile

Add CGO dependencies for crawshaw.io/sqlite:
- Build stages: `gcc musl-dev sqlite-dev`
- Production stage: `sqlite-libs` (runtime dependency)
- Change build command from `CGO_ENABLED=0` to `CGO_ENABLED=1`

### Step 6: Validation

1. **Unit tests**: `go test ./storage/...`
2. **Integration test**: Start ingestion, send spans via e2e_test_apps
3. **Load test**: Run orchestration with multiple services

## Validation Checklist

### Unit Tests
- [ ] Write single span, read it back
- [ ] Write multiple spans, read in order (ULID monotonic)
- [ ] Pagination works correctly (startKey filtering)
- [ ] Counter increments on write
- [ ] Counter decrements on read
- [ ] Counter reconciliation fixes drift
- [ ] Concurrent writes don't corrupt data
- [ ] Empty database returns empty results
- [ ] Corrupted span handling (log + skip)

### E2E Tests
- [ ] Single service workflow (`e2e_test_apps/app`)
- [ ] Multi-service concurrent (`e2e_test_apps/orchestration`)
- [ ] Backend can read spans via internal gRPC
- [ ] No cross-service pollution
- [ ] Graceful shutdown preserves data

### Performance (Baseline)
- [ ] Write throughput: measure spans/sec
- [ ] Read throughput: measure spans/sec
- [ ] Memory usage: should stay under 50MB
- [ ] Database size: measure growth rate

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JUNJO_WAL_SQLITE_PATH` | `~/.junjo/ingestion-wal/spans.db` | SQLite WAL database file path |
| `GRPC_PORT` | `50051` | Public gRPC port (unchanged) |

## Rollback Plan

If SQLite proves problematic:
1. Keep `badger.go` in place during development
2. Feature flag to switch between backends
3. Delete BadgerDB code only after full validation

## Next Steps (After Completion)

Once SQLite WAL is validated:
1. Implement Parquet flush from SQLite (Plan 002)
2. Add `ListSpans`, `GetTrace`, `GetServices` gRPC methods for live queries
