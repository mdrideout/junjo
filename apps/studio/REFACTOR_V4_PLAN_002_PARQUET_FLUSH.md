# Plan 002: Parquet Flush from SQLite

## Status: ✅ Complete

## Overview

This plan implements the Parquet flushing mechanism for the Go ingestion service. The flusher reads spans from the SQLite WAL buffer, converts them to Apache Arrow format, writes them to Parquet files on the local filesystem, and then deletes the flushed spans from SQLite.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Environment variable name | `SPAN_STORAGE_PATH` | Describes the data destination, not the process |
| Flush state tracking | Store first AND last keys | Enables potential re-flush for recovery scenarios |
| Post-flush behavior | DELETE from WAL | Keep SQLite as a buffer only, not permanent storage |
| Timestamp handling | UTC everywhere | Consistent date partitioning and time-related operations |
| Storage target | Local filesystem only | S3 support is a separate future phase |

## Implementation

### Files Created

| File | Purpose |
|------|---------|
| `ingestion/storage/parquet_writer.go` | Arrow schema definition, Parquet file writing with ZSTD compression |
| `ingestion/storage/parquet_writer_test.go` | Tests for Parquet writing functionality |
| `ingestion/storage/span_converter.go` | Converts OTLP protobuf spans to Arrow-compatible SpanRecord structs |
| `ingestion/storage/span_converter_test.go` | Tests for span conversion logic |
| `ingestion/storage/flusher.go` | Background flusher process with configurable triggers |
| `ingestion/storage/flusher_test.go` | Tests for flusher functionality |

### Files Modified

| File | Changes |
|------|---------|
| `ingestion/go.mod` | Added Apache Arrow/Parquet dependencies |
| `ingestion/storage/sqlite.go` | Added flush_state table, GetFlushState, UpdateFlushState, GetSpanCount methods |
| `ingestion/storage/sqlite_test.go` | Added tests for flush state operations |
| `ingestion/main.go` | Integrated flusher lifecycle (start/stop) |

## Arrow/Parquet Schema

```go
var SpanSchema = arrow.NewSchema(
    []arrow.Field{
        {Name: "span_id", Type: arrow.BinaryTypes.String, Nullable: false},
        {Name: "trace_id", Type: arrow.BinaryTypes.String, Nullable: false},
        {Name: "parent_span_id", Type: arrow.BinaryTypes.String, Nullable: true},
        {Name: "service_name", Type: arrow.BinaryTypes.String, Nullable: false},
        {Name: "name", Type: arrow.BinaryTypes.String, Nullable: false},
        {Name: "span_kind", Type: arrow.PrimitiveTypes.Int8, Nullable: false},
        {Name: "start_time", Type: TimestampNsUTC, Nullable: false},
        {Name: "end_time", Type: TimestampNsUTC, Nullable: false},
        {Name: "duration_ns", Type: arrow.PrimitiveTypes.Int64, Nullable: false},
        {Name: "status_code", Type: arrow.PrimitiveTypes.Int8, Nullable: false},
        {Name: "status_message", Type: arrow.BinaryTypes.String, Nullable: true},
        {Name: "attributes", Type: arrow.BinaryTypes.String, Nullable: false},        // JSON
        {Name: "events", Type: arrow.BinaryTypes.String, Nullable: false},            // JSON
        {Name: "resource_attributes", Type: arrow.BinaryTypes.String, Nullable: false}, // JSON
    },
    nil,
)
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SPAN_STORAGE_PATH` | `~/.junjo/spans` | Base directory for Parquet files |
| `FLUSH_INTERVAL` | `30s` | How often to check for flush conditions |
| `FLUSH_MAX_AGE` | `1h` | Maximum age before triggering flush |
| `FLUSH_MAX_ROWS` | `100000` | Maximum row count before triggering flush |
| `FLUSH_MIN_ROWS` | `1000` | Minimum rows required to flush (prevents tiny files) |

### Parquet Writer Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Compression | ZSTD level 3 | Good balance of compression ratio and speed |
| Row group size | 122,880 | Optimal for DataFusion query performance |

## Output Directory Structure

```
{SPAN_STORAGE_PATH}/
└── year=YYYY/
    └── month=MM/
        └── day=DD/
            └── {service}_{unix_timestamp}_{uuid8}.parquet
```

Example: `~/.junjo/spans/year=2024/month=01/day=15/chat-api_1705329600_a1b2c3d4.parquet`

## Flush Process

1. Check if flush conditions are met:
   - Row count exceeds `FLUSH_MAX_ROWS`, OR
   - Time since last flush exceeds `FLUSH_MAX_AGE`, AND
   - Row count meets minimum `FLUSH_MIN_ROWS`

2. Read all spans from SQLite (ordered by ULID key)

3. Convert each span from OTLP protobuf to SpanRecord:
   - Hex-encode binary IDs (trace_id, span_id, parent_span_id)
   - Extract service.name from resource attributes
   - Serialize attributes/events/resource_attributes to JSON

4. Write SpanRecords to Parquet file:
   - Create date-partitioned directory structure
   - Generate filename with service, timestamp, and UUID
   - Write with ZSTD compression

5. Delete flushed spans from SQLite (by key range)

6. Update flush_state table with:
   - Last flush time
   - First and last flushed keys
   - Cumulative flushed row count

## SQLite Schema Changes

```sql
CREATE TABLE IF NOT EXISTS flush_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_flush_time_unix INTEGER NOT NULL DEFAULT 0,
    first_flushed_key_ulid BLOB,
    last_flushed_key_ulid BLOB,
    total_flushed_rows INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO flush_state (id) VALUES (1);
```

## Graceful Shutdown

On SIGINT/SIGTERM:
1. Stop gRPC servers
2. Stop flusher (performs final flush of any remaining spans)
3. Sync database
4. Close database

## Testing

All tests pass:
- `TestWriteSpansToParquet` - Parquet writing with schema verification
- `TestWriteSpansToParquetEmptyRecords` - Error handling for empty input
- `TestWriteSpansToParquetCreatesDirectory` - Directory creation
- `TestConvertSpanDataToRecord` - Full span conversion
- `TestConvertSpanDataToRecord_RootSpan` - Root span (no parent) handling
- `TestConvertSpanDataToRecord_NoResource` - Missing resource handling
- `TestExtractServiceName` - Service name extraction edge cases
- `TestAnyValueToGo` - OTLP AnyValue type conversion
- `TestKeyValuesToJSON` - Attribute serialization
- `TestEventsToJSON` - Event serialization
- `TestFlusherFlush` - Full flush cycle
- `TestFlusherCheckAndFlush_RowCountThreshold` - Row count trigger
- `TestFlusherCheckAndFlush_MinRowCount` - Minimum row protection
- `TestFlusherCheckAndFlush_NoSpans` - Empty database handling
- `TestFlusherStartStop` - Background process lifecycle
- `TestGenerateOutputPath` - Path generation with date partitioning
- `TestSanitizeServiceName` - Filesystem-safe service names

## Dependencies Added

```
github.com/apache/arrow/go/v18 v18.2.0
```

This includes:
- `arrow` - Core Arrow types and schemas
- `arrow/array` - Array builders for record batch construction
- `arrow/memory` - Memory allocation
- `parquet` - Parquet file format support
- `parquet/compress` - Compression codecs (ZSTD)
- `parquet/pqarrow` - Arrow-to-Parquet bridge

## Post-Implementation Cleanup

After initial implementation, an architectural consistency pass was performed:

### Config: Global Singleton Pattern

Changed from dependency injection to global singleton:

```go
// Before: Pass config to each constructor
authClient, err := backend_client.NewAuthClient(cfg.Backend)
flusher := storage.NewFlusher(repo, flusherConfig)
server.NewGRPCServer(repo, authClient, log, cfg.Server)

// After: Components call config.Get() internally
authClient, err := backend_client.NewAuthClient()
flusher := storage.NewFlusher(repo)
server.NewGRPCServer(repo, authClient)
```

Added to `config/config.go`:
- `Get()` - Returns global config singleton, loads on first call
- `MustLoad()` - Call at startup, panics on error
- `SetForTesting()` - Allows tests to set custom config

### Logging: Global slog Only

Changed from passing `*slog.Logger` to using global `slog`:

```go
// Before
func NewGRPCServer(repo storage.SpanRepository, authClient *backend_client.AuthClient, log *slog.Logger, cfg config.ServerConfig)

// After
func NewGRPCServer(repo storage.SpanRepository, authClient *backend_client.AuthClient)
```

- `logger.Init()` calls `slog.SetDefault()` once at startup
- All code uses `slog.Info()`, `slog.Error()`, etc. directly
- Removed duplicate flusher config logging from `main.go`

### Removed Deprecated Cruft

Since this is greenfield V4, removed unnecessary backward compatibility:

| Removed | From |
|---------|------|
| `type Storage = SQLiteRepository` | `storage/repository.go` |
| `func NewStorage()` | `storage/repository.go` |
| `func NewOtelTraceService(store *storage.Storage)` | `server/otel_trace_service.go` |
| `func NewWALReaderService(store *storage.Storage)` | `server/wal_reader_service.go` |
| `FlusherConfigFromConfig()` | `storage/flusher.go` |

### Files Modified in Cleanup

| File | Changes |
|------|---------|
| `config/config.go` | Added `Get()`, `MustLoad()`, `SetForTesting()` |
| `logger/logger.go` | `InitLogger(cfg)` → `Init()` |
| `main.go` | Simplified startup, removed duplicate logging |
| `server/server.go` | Removed `log` and `cfg` parameters |
| `storage/flusher.go` | Removed config parameter, uses `config.Get()` |
| `storage/flusher_test.go` | Uses `config.SetForTesting()` |
| `backend_client/auth_client.go` | Removed `cfg` parameter |

## Next Steps

- **Plan 003**: Python backend Parquet indexer - Poll for new Parquet files, extract span summaries, update DuckDB metadata
