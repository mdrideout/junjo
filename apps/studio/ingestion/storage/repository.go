package storage

import (
	"crypto/rand"
	"fmt"
	"log/slog"
	"sync"
	"sync/atomic"
	"time"

	"crawshaw.io/sqlite"
	"crawshaw.io/sqlite/sqlitex"
	"github.com/oklog/ulid/v2"
	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/proto"

	"junjo-ai-studio/ingestion/config"
)

// SpanFilter defines filtering options for WAL span queries.
type SpanFilter struct {
	TraceID      string // Filter by trace ID (exact match)
	ServiceName  string // Filter by service name (exact match)
	RootOnly     bool   // Only return root spans (no parent)
	WorkflowOnly bool   // Only return workflow spans (junjo.span_type = 'workflow')
	Limit        int    // Maximum number of spans to return (0 = no limit)
}

// SpanWriteRequest contains all data needed to write a span in a batch.
type SpanWriteRequest struct {
	Span     *tracepb.Span
	Resource *resourcepb.Resource
}

// SpanRepository defines the data access interface for span storage.
type SpanRepository interface {
	// Span operations
	WriteSpan(span *tracepb.Span, resource *resourcepb.Resource) error
	WriteSpans(requests []*SpanWriteRequest) error // Batch write - much more efficient
	ReadSpans(startKey []byte, batchSize uint32, sendFunc func(key, spanBytes, resourceBytes []byte) error) (lastKeyProcessed []byte, corruptedCount uint32, err error)
	DeleteSpansInRange(firstKey, lastKey []byte) error
	GetSpanCount() (int64, error)
	ReadAllSpansForFlush() (records []SpanRecord, firstKey, lastKey []byte, err error)

	// Streaming flush operations (memory-bounded)
	// Returns pooled slice pointer - caller MUST call ReleaseSpanRecords() when done
	ReadSpansChunked(startKey []byte, chunkSize int) (records *[]SpanRecord, firstKey, lastKey []byte, hasMore bool, err error)

	// WAL Query operations (unified Arrow-based query)
	GetSpansFiltered(filter SpanFilter) ([]SpanRecord, error)
	GetDistinctServiceNames() ([]string, error)

	// Counter operations
	GetUnretrievedCount() (uint64, error)
	DecrementAndGetCount(n uint32) (uint64, error)
	ReconcileCount() error

	// Cold flush state
	GetFlushState() (*FlushState, error)
	UpdateFlushState(firstKey, lastKey []byte, rowsFlushed int64) error
	GetDBSize() (int64, error)
	GetSpanDataSize() (int64, error) // Returns actual span data bytes (not DB file size)

	// Reactive byte tracking (for non-polling cold flush)
	GetBytesSinceCold() int64                // Returns current atomic counter (fast, no query)
	ResetBytesSinceCold()                    // Reset counter after cold flush
	SetColdSignalChannel(ch chan<- struct{}) // Set channel to signal when threshold exceeded

	// Lifecycle
	Sync() error
	Close() error
}

// --- sync.Pool for SpanRecord slices ---
// Reduces GC pressure during streaming flush by reusing slice allocations

var spanRecordPool = sync.Pool{
	New: func() interface{} {
		// Pre-allocate slice with default chunk capacity
		// Default: 25MB / 10 chunks / 500 bytes avg = ~5,000 spans
		s := make([]SpanRecord, 0, 5000)
		return &s
	},
}

// getSpanRecordSlice gets a slice from the pool with the given capacity.
func getSpanRecordSlice(capacity int) *[]SpanRecord {
	s := spanRecordPool.Get().(*[]SpanRecord)
	// Ensure capacity is sufficient
	if cap(*s) < capacity {
		*s = make([]SpanRecord, 0, capacity)
	} else {
		*s = (*s)[:0] // Reset length, keep capacity
	}
	return s
}

// ReleaseSpanRecords returns a slice to the pool for reuse.
// Call this after you're done processing a chunk of SpanRecords.
func ReleaseSpanRecords(records *[]SpanRecord) {
	if records == nil {
		return
	}
	// Clear slice to allow GC of SpanRecord contents
	*records = (*records)[:0]
	spanRecordPool.Put(records)
}

// --- Monotonic ULID Generator ---

var (
	ulidGenerator = struct {
		sync.Mutex
		*ulid.MonotonicEntropy
	}{
		MonotonicEntropy: ulid.Monotonic(rand.Reader, 0),
	}
)

func newULID() (ulid.ULID, error) {
	ulidGenerator.Lock()
	defer ulidGenerator.Unlock()
	return ulid.New(ulid.Timestamp(time.Now()), &ulidGenerator)
}

// newULIDs generates multiple ULIDs under a single lock acquisition.
// This is much more efficient than calling newULID() in a loop.
func newULIDs(count int) ([]ulid.ULID, error) {
	if count == 0 {
		return nil, nil
	}

	ulidGenerator.Lock()
	defer ulidGenerator.Unlock()

	ids := make([]ulid.ULID, count)
	now := ulid.Timestamp(time.Now())
	for i := 0; i < count; i++ {
		id, err := ulid.New(now, &ulidGenerator)
		if err != nil {
			return nil, err
		}
		ids[i] = id
	}
	return ids, nil
}

// --- SQLiteRepository Implementation ---

// SQLiteRepository implements SpanRepository using SQLite.
type SQLiteRepository struct {
	pool *sqlitex.Pool

	// Reactive byte tracking for cold flush (triggers when threshold exceeded)
	bytesSinceCold     atomic.Int64    // Tracks bytes written since last cold flush
	coldSignalCh       chan<- struct{} // Channel to signal when cold threshold exceeded
	coldSignalMu       sync.RWMutex    // Protects coldSignalCh
	coldBytesThreshold int64           // Threshold in bytes to trigger cold signal
}

// NewSQLiteRepository creates a new SQLiteRepository at the specified path.
func NewSQLiteRepository(path string) (*SQLiteRepository, error) {
	// Open connection pool with 10 connections
	// URI format enables WAL mode and other pragmas
	uri := fmt.Sprintf("file:%s?_journal_mode=WAL&_busy_timeout=5000&_synchronous=NORMAL", path)
	pool, err := sqlitex.Open(uri, 0, 10)
	if err != nil {
		return nil, fmt.Errorf("failed to open sqlite pool: %w", err)
	}

	slog.Info("sqlite opened", slog.String("path", path))

	// Get flush thresholds from config
	cfg := config.Get().Flusher
	repo := &SQLiteRepository{
		pool:               pool,
		coldBytesThreshold: cfg.MaxBytes, // Triggers cold flush when exceeded
	}

	// Initialize schema
	if err := repo.initSchema(); err != nil {
		pool.Close()
		return nil, fmt.Errorf("failed to initialize schema: %w", err)
	}

	// Perform initial reconciliation on startup
	if err := repo.ReconcileCount(); err != nil {
		slog.Warn("Initial counter reconciliation failed", slog.Any("error", err))
	}

	// Start periodic reconciliation (every 60 minutes)
	go func() {
		ticker := time.NewTicker(60 * time.Minute)
		defer ticker.Stop()
		for range ticker.C {
			if err := repo.ReconcileCount(); err != nil {
				slog.Error("Periodic counter reconciliation failed", slog.Any("error", err))
			}
		}
	}()

	return repo, nil
}

// initSchema creates the database tables if they don't exist.
func (r *SQLiteRepository) initSchema() error {
	conn := r.pool.Get(nil)
	if conn == nil {
		return fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	err := sqlitex.ExecScript(conn, `
		CREATE TABLE IF NOT EXISTS spans (
			key_ulid BLOB PRIMARY KEY,
			span_bytes BLOB NOT NULL,
			resource_bytes BLOB,
			-- Indexed columns for WAL queries (extracted from span_bytes for efficient lookup)
			trace_id TEXT,
			service_name TEXT,
			parent_span_id TEXT,
			start_time_unix_nano INTEGER
		) WITHOUT ROWID;

		-- Indexes for WAL query operations
		CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id);
		CREATE INDEX IF NOT EXISTS idx_spans_service_name ON spans(service_name);
		CREATE INDEX IF NOT EXISTS idx_spans_parent_span_id ON spans(parent_span_id);

		CREATE TABLE IF NOT EXISTS metadata (
			key TEXT PRIMARY KEY,
			value INTEGER NOT NULL
		);

		INSERT OR IGNORE INTO metadata (key, value) VALUES ('unretrieved_count', 0);

		CREATE TABLE IF NOT EXISTS flush_state (
			id INTEGER PRIMARY KEY CHECK (id = 1),
			last_flush_time_unix INTEGER NOT NULL DEFAULT 0,
			first_flushed_key_ulid BLOB,
			last_flushed_key_ulid BLOB,
			total_flushed_rows INTEGER NOT NULL DEFAULT 0
		);

		INSERT OR IGNORE INTO flush_state (id) VALUES (1);

		-- Warm snapshot state tracks incremental snapshots to tmp parquet files
		-- These are smaller, more frequent snapshots between full flushes
		CREATE TABLE IF NOT EXISTS warm_snapshot_state (
			id INTEGER PRIMARY KEY CHECK (id = 1),
			last_warm_ulid BLOB,              -- Last span ULID written to warm snapshot
			last_warm_time_ns INTEGER NOT NULL DEFAULT 0,  -- Timestamp of last warm snapshot
			warm_file_count INTEGER NOT NULL DEFAULT 0     -- Number of warm parquet files
		);

		INSERT OR IGNORE INTO warm_snapshot_state (id, last_warm_ulid, last_warm_time_ns, warm_file_count)
		VALUES (1, NULL, 0, 0);
	`)
	if err != nil {
		return fmt.Errorf("failed to create schema: %w", err)
	}

	return nil
}

// Close safely closes the SQLite connection pool.
func (r *SQLiteRepository) Close() error {
	slog.Info("closing sqlite")
	return r.pool.Close()
}

// Sync is a no-op for SQLite WAL mode - writes are already durable.
func (r *SQLiteRepository) Sync() error {
	slog.Info("sqlite sync (no-op in WAL mode)")
	return nil
}

// WriteSpan serializes a span and resource and writes them to SQLite.
func (r *SQLiteRepository) WriteSpan(span *tracepb.Span, resource *resourcepb.Resource) error {
	conn := r.pool.Get(nil)
	if conn == nil {
		return fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	// Create SpanData and serialize
	spanData := &SpanData{
		Span:     span,
		Resource: resource,
	}
	dataBytes, err := MarshalSpanData(spanData)
	if err != nil {
		return err
	}

	// Generate monotonic ULID
	key, err := newULID()
	if err != nil {
		return fmt.Errorf("failed to generate ULID: %w", err)
	}

	// Extract indexed fields from span and resource
	traceID := fmt.Sprintf("%x", span.GetTraceId())
	parentSpanID := fmt.Sprintf("%x", span.GetParentSpanId())
	if len(span.GetParentSpanId()) == 0 {
		parentSpanID = "" // Root span has no parent
	}
	startTimeUnixNano := int64(span.GetStartTimeUnixNano())

	// Extract service name from resource attributes
	serviceName := ""
	if resource != nil {
		for _, attr := range resource.GetAttributes() {
			if attr.GetKey() == "service.name" {
				serviceName = attr.GetValue().GetStringValue()
				break
			}
		}
	}

	// Begin transaction
	defer sqlitex.Save(conn)(&err)

	// Insert span with indexed columns
	stmt := conn.Prep(`INSERT INTO spans (key_ulid, span_bytes, trace_id, service_name, parent_span_id, start_time_unix_nano) VALUES (?, ?, ?, ?, ?, ?)`)
	stmt.BindBytes(1, key[:])
	stmt.BindBytes(2, dataBytes)
	stmt.BindText(3, traceID)
	stmt.BindText(4, serviceName)
	stmt.BindText(5, parentSpanID)
	stmt.BindInt64(6, startTimeUnixNano)

	_, err = stmt.Step()
	stmt.Reset()
	if err != nil {
		return fmt.Errorf("failed to insert span: %w", err)
	}

	// Increment counter
	stmt = conn.Prep(`UPDATE metadata SET value = value + 1 WHERE key = ?`)
	stmt.BindText(1, MetadataKeyUnretrievedCount)
	_, err = stmt.Step()
	stmt.Reset()
	if err != nil {
		return fmt.Errorf("failed to increment counter: %w", err)
	}

	return nil
}

// WriteSpans writes multiple spans in a single transaction.
// This is much more efficient than calling WriteSpan() in a loop.
// Also tracks bytes written and signals warm flusher when threshold exceeded.
func (r *SQLiteRepository) WriteSpans(requests []*SpanWriteRequest) error {
	if len(requests) == 0 {
		return nil
	}

	conn := r.pool.Get(nil)
	if conn == nil {
		return fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	// Pre-generate all ULIDs at once (single mutex acquisition)
	keys, err := newULIDs(len(requests))
	if err != nil {
		return fmt.Errorf("failed to generate ULIDs: %w", err)
	}

	// Begin transaction
	defer sqlitex.Save(conn)(&err)

	// Prepare statement once, reuse for all inserts
	stmt := conn.Prep(`INSERT INTO spans (key_ulid, span_bytes, trace_id, service_name, parent_span_id, start_time_unix_nano) VALUES (?, ?, ?, ?, ?, ?)`)
	defer stmt.Reset()

	// Track total bytes in this batch for reactive warm triggering
	var batchBytes int64

	for i, req := range requests {
		// Create SpanData and serialize
		spanData := &SpanData{
			Span:     req.Span,
			Resource: req.Resource,
		}
		dataBytes, err := MarshalSpanData(spanData)
		if err != nil {
			return fmt.Errorf("failed to marshal span %d: %w", i, err)
		}

		// Track bytes for reactive warm triggering
		batchBytes += int64(len(dataBytes))

		// Extract indexed fields from span and resource
		traceID := fmt.Sprintf("%x", req.Span.GetTraceId())
		parentSpanID := ""
		if len(req.Span.GetParentSpanId()) > 0 {
			parentSpanID = fmt.Sprintf("%x", req.Span.GetParentSpanId())
		}
		startTimeUnixNano := int64(req.Span.GetStartTimeUnixNano())

		// Extract service name from resource attributes
		serviceName := ""
		if req.Resource != nil {
			for _, attr := range req.Resource.GetAttributes() {
				if attr.GetKey() == "service.name" {
					serviceName = attr.GetValue().GetStringValue()
					break
				}
			}
		}

		// Bind parameters
		stmt.BindBytes(1, keys[i][:])
		stmt.BindBytes(2, dataBytes)
		stmt.BindText(3, traceID)
		stmt.BindText(4, serviceName)
		stmt.BindText(5, parentSpanID)
		stmt.BindInt64(6, startTimeUnixNano)

		// Execute insert
		if _, err = stmt.Step(); err != nil {
			return fmt.Errorf("failed to insert span %d: %w", i, err)
		}
		stmt.Reset()
	}

	// Update atomic byte counter and check if we should signal cold flush
	newColdTotal := r.bytesSinceCold.Add(batchBytes)
	if newColdTotal >= r.coldBytesThreshold {
		r.signalColdFlush()
	}

	// Single counter update for entire batch
	countStmt := conn.Prep(`UPDATE metadata SET value = value + ? WHERE key = ?`)
	countStmt.BindInt64(1, int64(len(requests)))
	countStmt.BindText(2, MetadataKeyUnretrievedCount)
	_, err = countStmt.Step()
	countStmt.Reset()
	if err != nil {
		return fmt.Errorf("failed to increment counter: %w", err)
	}

	return nil
}

// ReadSpans reads spans from the database starting after startKey.
func (r *SQLiteRepository) ReadSpans(startKey []byte, batchSize uint32, sendFunc func(key, spanBytes, resourceBytes []byte) error) (lastKeyProcessed []byte, corruptedCount uint32, err error) {
	conn := r.pool.Get(nil)
	if conn == nil {
		return nil, 0, fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	var stmt *sqlite.Stmt
	if len(startKey) == 0 {
		stmt = conn.Prep(`SELECT key_ulid, span_bytes FROM spans ORDER BY key_ulid LIMIT ?`)
		stmt.BindInt64(1, int64(batchSize))
	} else {
		stmt = conn.Prep(`SELECT key_ulid, span_bytes FROM spans WHERE key_ulid > ? ORDER BY key_ulid LIMIT ?`)
		stmt.BindBytes(1, startKey)
		stmt.BindInt64(2, int64(batchSize))
	}
	defer stmt.Reset()

	for {
		hasRow, err := stmt.Step()
		if err != nil {
			return lastKeyProcessed, corruptedCount, fmt.Errorf("failed to step: %w", err)
		}
		if !hasRow {
			break
		}

		// Read key
		keyLen := stmt.ColumnLen(0)
		key := make([]byte, keyLen)
		stmt.ColumnBytes(0, key)
		lastKeyProcessed = key

		// Read span data
		dataLen := stmt.ColumnLen(1)
		dataBytes := make([]byte, dataLen)
		stmt.ColumnBytes(1, dataBytes)

		// Unmarshal span data
		spanData, err := UnmarshalSpanData(dataBytes)
		if err != nil {
			slog.Warn("error unmarshaling span data",
				slog.String("key", fmt.Sprintf("%x", key)),
				slog.Any("error", err))
			corruptedCount++
			continue
		}

		// Marshal span and resource back to bytes for sending
		spanBytes, err := proto.Marshal(spanData.Span)
		if err != nil {
			slog.Warn("error marshaling span",
				slog.String("key", fmt.Sprintf("%x", key)),
				slog.Any("error", err))
			corruptedCount++
			continue
		}
		resourceBytes, err := proto.Marshal(spanData.Resource)
		if err != nil {
			slog.Warn("error marshaling resource",
				slog.String("key", fmt.Sprintf("%x", key)),
				slog.Any("error", err))
			corruptedCount++
			continue
		}

		// Send to callback
		if err := sendFunc(key, spanBytes, resourceBytes); err != nil {
			return lastKeyProcessed, corruptedCount, err
		}
	}

	return lastKeyProcessed, corruptedCount, nil
}

// DeleteSpansInRange deletes all spans with keys between firstKey and lastKey (inclusive).
func (r *SQLiteRepository) DeleteSpansInRange(firstKey, lastKey []byte) error {
	conn := r.pool.Get(nil)
	if conn == nil {
		return fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	stmt := conn.Prep(`DELETE FROM spans WHERE key_ulid >= ? AND key_ulid <= ?`)
	defer stmt.Reset()

	stmt.BindBytes(1, firstKey)
	stmt.BindBytes(2, lastKey)

	_, err := stmt.Step()
	if err != nil {
		return fmt.Errorf("failed to delete spans: %w", err)
	}

	return nil
}

// GetSpanCount returns the total number of spans in the database.
func (r *SQLiteRepository) GetSpanCount() (int64, error) {
	conn := r.pool.Get(nil)
	if conn == nil {
		return 0, fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	stmt := conn.Prep(`SELECT COUNT(*) FROM spans`)
	defer stmt.Reset()

	hasRow, err := stmt.Step()
	if err != nil {
		return 0, fmt.Errorf("failed to count spans: %w", err)
	}
	if !hasRow {
		return 0, nil
	}

	return stmt.ColumnInt64(0), nil
}

// ReadAllSpansForFlush reads all spans from SQLite and converts them to SpanRecords.
func (r *SQLiteRepository) ReadAllSpansForFlush() ([]SpanRecord, []byte, []byte, error) {
	var records []SpanRecord
	var firstKey, lastKey []byte

	conn := r.pool.Get(nil)
	if conn == nil {
		return nil, nil, nil, fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	stmt := conn.Prep(`SELECT key_ulid, span_bytes FROM spans ORDER BY key_ulid`)
	defer stmt.Reset()

	for {
		hasRow, err := stmt.Step()
		if err != nil {
			return nil, nil, nil, fmt.Errorf("failed to step: %w", err)
		}
		if !hasRow {
			break
		}

		// Read key
		keyLen := stmt.ColumnLen(0)
		key := make([]byte, keyLen)
		stmt.ColumnBytes(0, key)

		if firstKey == nil {
			firstKey = key
		}
		lastKey = key

		// Read span data
		dataLen := stmt.ColumnLen(1)
		dataBytes := make([]byte, dataLen)
		stmt.ColumnBytes(1, dataBytes)

		// Unmarshal span data
		spanData, err := UnmarshalSpanData(dataBytes)
		if err != nil {
			slog.Warn("error unmarshaling span data during flush, skipping",
				slog.String("key", fmt.Sprintf("%x", key)),
				slog.Any("error", err))
			continue
		}

		// Convert to record
		record := ConvertSpanDataToRecord(spanData)
		records = append(records, record)
	}

	return records, firstKey, lastKey, nil
}

// --- Counter Operations ---

// GetUnretrievedCount returns the current unretrieved span count.
func (r *SQLiteRepository) GetUnretrievedCount() (uint64, error) {
	conn := r.pool.Get(nil)
	if conn == nil {
		return 0, fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	stmt := conn.Prep(`SELECT value FROM metadata WHERE key = ?`)
	defer stmt.Reset()
	stmt.BindText(1, MetadataKeyUnretrievedCount)

	hasRow, err := stmt.Step()
	if err != nil {
		return 0, fmt.Errorf("failed to get count: %w", err)
	}
	if !hasRow {
		return 0, nil
	}

	return uint64(stmt.ColumnInt64(0)), nil
}

// DecrementAndGetCount decrements the span counter by n and returns the remaining count.
func (r *SQLiteRepository) DecrementAndGetCount(n uint32) (uint64, error) {
	conn := r.pool.Get(nil)
	if conn == nil {
		return 0, fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	var remaining uint64
	var err error
	defer sqlitex.Save(conn)(&err)

	// Get current count
	stmt := conn.Prep(`SELECT value FROM metadata WHERE key = ?`)
	stmt.BindText(1, MetadataKeyUnretrievedCount)

	hasRow, err := stmt.Step()
	if err != nil {
		stmt.Reset()
		return 0, fmt.Errorf("failed to get count: %w", err)
	}
	if !hasRow {
		stmt.Reset()
		return 0, nil
	}

	count := uint64(stmt.ColumnInt64(0))
	stmt.Reset()

	// Decrement with underflow protection
	if count >= uint64(n) {
		count -= uint64(n)
	} else {
		slog.Warn("Counter underflow prevented",
			slog.Uint64("current", count),
			slog.Uint64("decrement", uint64(n)))
		count = 0
	}
	remaining = count

	// Update counter
	stmt = conn.Prep(`UPDATE metadata SET value = ? WHERE key = ?`)
	stmt.BindInt64(1, int64(count))
	stmt.BindText(2, MetadataKeyUnretrievedCount)

	_, err = stmt.Step()
	stmt.Reset()
	if err != nil {
		return 0, fmt.Errorf("failed to update count: %w", err)
	}

	return remaining, nil
}

// ReconcileCount counts actual spans and corrects the counter if drift is detected.
func (r *SQLiteRepository) ReconcileCount() error {
	conn := r.pool.Get(nil)
	if conn == nil {
		return fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	// Count actual spans
	stmt := conn.Prep(`SELECT COUNT(*) FROM spans`)
	hasRow, err := stmt.Step()
	if err != nil {
		stmt.Reset()
		return fmt.Errorf("failed to count spans: %w", err)
	}
	if !hasRow {
		stmt.Reset()
		return fmt.Errorf("no result from COUNT(*)")
	}
	actualCount := uint64(stmt.ColumnInt64(0))
	stmt.Reset()

	// Get stored counter (uses its own connection from pool)
	storedCount, err := r.GetUnretrievedCount()
	if err != nil {
		return err
	}

	// Check for drift
	if actualCount != storedCount {
		drift := int64(actualCount) - int64(storedCount)
		slog.Warn("Counter drift detected during reconciliation",
			slog.Uint64("actual_count", actualCount),
			slog.Uint64("stored_count", storedCount),
			slog.Int64("drift", drift))

		// Correct the counter
		stmt = conn.Prep(`UPDATE metadata SET value = ? WHERE key = ?`)
		stmt.BindInt64(1, int64(actualCount))
		stmt.BindText(2, MetadataKeyUnretrievedCount)

		_, err = stmt.Step()
		stmt.Reset()
		if err != nil {
			return fmt.Errorf("failed to update count: %w", err)
		}
		return nil
	}

	slog.Info("Counter reconciliation completed, no drift detected",
		slog.Uint64("count", actualCount))
	return nil
}

// --- Flush State Operations ---

// GetFlushState returns the current flush state.
func (r *SQLiteRepository) GetFlushState() (*FlushState, error) {
	conn := r.pool.Get(nil)
	if conn == nil {
		return nil, fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	stmt := conn.Prep(`SELECT last_flush_time_unix, first_flushed_key_ulid, last_flushed_key_ulid, total_flushed_rows FROM flush_state WHERE id = 1`)
	defer stmt.Reset()

	hasRow, err := stmt.Step()
	if err != nil {
		return nil, fmt.Errorf("failed to get flush state: %w", err)
	}
	if !hasRow {
		// Should never happen due to INSERT OR IGNORE in schema
		return &FlushState{}, nil
	}

	// Get unix timestamp - 0 means never flushed
	lastFlushUnix := stmt.ColumnInt64(0)
	var lastFlushTime time.Time
	if lastFlushUnix > 0 {
		lastFlushTime = time.Unix(lastFlushUnix, 0).UTC()
	}
	// else: lastFlushTime remains zero value, so IsZero() returns true

	state := &FlushState{
		LastFlushTime:    lastFlushTime,
		TotalFlushedRows: stmt.ColumnInt64(3),
	}

	// Read first flushed key (may be NULL)
	if stmt.ColumnLen(1) > 0 {
		state.FirstFlushedKey = make([]byte, stmt.ColumnLen(1))
		stmt.ColumnBytes(1, state.FirstFlushedKey)
	}

	// Read last flushed key (may be NULL)
	if stmt.ColumnLen(2) > 0 {
		state.LastFlushedKey = make([]byte, stmt.ColumnLen(2))
		stmt.ColumnBytes(2, state.LastFlushedKey)
	}

	return state, nil
}

// UpdateFlushState updates the flush state after a successful flush.
func (r *SQLiteRepository) UpdateFlushState(firstKey, lastKey []byte, rowsFlushed int64) error {
	conn := r.pool.Get(nil)
	if conn == nil {
		return fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	stmt := conn.Prep(`
		UPDATE flush_state
		SET last_flush_time_unix = ?,
			first_flushed_key_ulid = ?,
			last_flushed_key_ulid = ?,
			total_flushed_rows = total_flushed_rows + ?
		WHERE id = 1
	`)
	defer stmt.Reset()

	stmt.BindInt64(1, time.Now().UTC().Unix())
	stmt.BindBytes(2, firstKey)
	stmt.BindBytes(3, lastKey)
	stmt.BindInt64(4, rowsFlushed)

	_, err := stmt.Step()
	if err != nil {
		return fmt.Errorf("failed to update flush state: %w", err)
	}

	return nil
}

// GetDBSize returns the current SQLite database size in bytes.
// Uses PRAGMA page_count * page_size which is more accurate than file size.
func (r *SQLiteRepository) GetDBSize() (int64, error) {
	conn := r.pool.Get(nil)
	if conn == nil {
		return 0, fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	stmt := conn.Prep(`SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()`)
	defer stmt.Reset()

	if hasRow, err := stmt.Step(); err != nil {
		return 0, fmt.Errorf("failed to query DB size: %w", err)
	} else if !hasRow {
		return 0, fmt.Errorf("no result from DB size query")
	}

	return stmt.ColumnInt64(0), nil
}

// GetSpanDataSize returns the total size of span data in bytes.
// This is the actual data size (sum of span_bytes), not the DB file size.
// More accurate for backpressure since DB file doesn't shrink on delete.
func (r *SQLiteRepository) GetSpanDataSize() (int64, error) {
	conn := r.pool.Get(nil)
	if conn == nil {
		return 0, fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	stmt := conn.Prep(`SELECT COALESCE(SUM(LENGTH(span_bytes)), 0) FROM spans`)
	defer stmt.Reset()

	if hasRow, err := stmt.Step(); err != nil {
		return 0, fmt.Errorf("failed to query span data size: %w", err)
	} else if !hasRow {
		return 0, nil
	}

	return stmt.ColumnInt64(0), nil
}

// --- WAL Query Operations ---

// GetSpansFiltered returns spans matching the filter criteria as SpanRecords.
// This is the unified query method for Arrow-based data transfer.
func (r *SQLiteRepository) GetSpansFiltered(filter SpanFilter) ([]SpanRecord, error) {
	conn := r.pool.Get(nil)
	if conn == nil {
		return nil, fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	// Build dynamic SQL query based on filters
	query := `SELECT span_bytes FROM spans WHERE 1=1`
	var params []any

	if filter.TraceID != "" {
		query += ` AND trace_id = ?`
		params = append(params, filter.TraceID)
	}

	if filter.ServiceName != "" {
		query += ` AND service_name = ?`
		params = append(params, filter.ServiceName)
	}

	if filter.RootOnly {
		query += ` AND (parent_span_id IS NULL OR parent_span_id = '')`
	}

	// Order by time
	query += ` ORDER BY start_time_unix_nano DESC`

	// Apply limit if specified (we may need to fetch more for workflow filtering)
	fetchLimit := filter.Limit
	if filter.WorkflowOnly && fetchLimit > 0 {
		// Fetch more to account for in-memory filtering
		fetchLimit = fetchLimit * 3
		if fetchLimit > 5000 {
			fetchLimit = 5000
		}
	}
	if fetchLimit > 0 {
		query += fmt.Sprintf(` LIMIT %d`, fetchLimit)
	}

	stmt := conn.Prep(query)
	defer stmt.Reset()

	// Bind parameters
	for i, param := range params {
		stmt.BindText(i+1, param.(string))
	}

	var records []SpanRecord
	for {
		hasRow, err := stmt.Step()
		if err != nil {
			return nil, fmt.Errorf("failed to query spans: %w", err)
		}
		if !hasRow {
			break
		}

		// Read span data
		dataLen := stmt.ColumnLen(0)
		dataBytes := make([]byte, dataLen)
		stmt.ColumnBytes(0, dataBytes)

		// Unmarshal span data
		spanData, err := UnmarshalSpanData(dataBytes)
		if err != nil {
			slog.Warn("error unmarshaling span data in GetSpansFiltered, skipping",
				slog.Any("error", err))
			continue
		}

		// Apply workflow filter in memory if needed
		if filter.WorkflowOnly {
			isWorkflow := false
			for _, attr := range spanData.Span.GetAttributes() {
				if attr.GetKey() == "junjo.span_type" {
					if attr.GetValue().GetStringValue() == "workflow" {
						isWorkflow = true
					}
					break
				}
			}
			if !isWorkflow {
				continue
			}
		}

		// Convert to SpanRecord
		record := ConvertSpanDataToRecord(spanData)
		records = append(records, record)

		// Check if we've reached the actual limit
		if filter.Limit > 0 && len(records) >= filter.Limit {
			break
		}
	}

	return records, nil
}

// GetDistinctServiceNames returns all distinct service names currently in the WAL.
func (r *SQLiteRepository) GetDistinctServiceNames() ([]string, error) {
	conn := r.pool.Get(nil)
	if conn == nil {
		return nil, fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	stmt := conn.Prep(`SELECT DISTINCT service_name FROM spans WHERE service_name IS NOT NULL AND service_name != '' ORDER BY service_name`)
	defer stmt.Reset()

	var services []string
	for {
		hasRow, err := stmt.Step()
		if err != nil {
			return nil, fmt.Errorf("failed to get distinct service names: %w", err)
		}
		if !hasRow {
			break
		}

		serviceName := stmt.ColumnText(0)
		services = append(services, serviceName)
	}

	return services, nil
}

// --- Reactive Cold Flush Byte Tracking ---

// signalColdFlush sends a non-blocking signal to the cold flush channel.
// Called when byte threshold is exceeded.
func (r *SQLiteRepository) signalColdFlush() {
	r.coldSignalMu.RLock()
	ch := r.coldSignalCh
	r.coldSignalMu.RUnlock()

	if ch != nil {
		// Non-blocking send - if channel is full, skip (cold flush already pending)
		select {
		case ch <- struct{}{}:
			slog.Debug("cold flush signal sent",
				slog.Int64("bytes_since_cold", r.bytesSinceCold.Load()),
				slog.Int64("threshold", r.coldBytesThreshold))
		default:
			// Channel full, cold flush already signaled
		}
	}
}

// GetBytesSinceCold returns the current cold byte counter (fast, no query).
func (r *SQLiteRepository) GetBytesSinceCold() int64 {
	return r.bytesSinceCold.Load()
}

// ResetBytesSinceCold resets the cold byte counter after a cold flush.
func (r *SQLiteRepository) ResetBytesSinceCold() {
	r.bytesSinceCold.Store(0)
}

// SetColdSignalChannel sets the channel to signal when cold threshold is exceeded.
func (r *SQLiteRepository) SetColdSignalChannel(ch chan<- struct{}) {
	r.coldSignalMu.Lock()
	r.coldSignalCh = ch
	r.coldSignalMu.Unlock()
}

// ReadSpansChunked reads a chunk of spans for streaming flush.
// Uses cursor-based pagination to bound memory usage.
// Returns a pooled slice - caller MUST call ReleaseSpanRecords() when done.
func (r *SQLiteRepository) ReadSpansChunked(startKey []byte, chunkSize int) (*[]SpanRecord, []byte, []byte, bool, error) {
	conn := r.pool.Get(nil)
	if conn == nil {
		return nil, nil, nil, false, fmt.Errorf("failed to get connection from pool")
	}
	defer r.pool.Put(conn)

	// Get pooled slice
	records := getSpanRecordSlice(chunkSize)

	var firstKey, lastKey []byte
	var stmt *sqlite.Stmt

	// Read chunkSize+1 to detect if there's more data
	if startKey == nil {
		// First chunk - no cursor
		stmt = conn.Prep(`SELECT key_ulid, span_bytes FROM spans ORDER BY key_ulid LIMIT ?`)
		stmt.BindInt64(1, int64(chunkSize+1))
	} else {
		// Subsequent chunks - use cursor (exclusive >)
		stmt = conn.Prep(`SELECT key_ulid, span_bytes FROM spans WHERE key_ulid > ? ORDER BY key_ulid LIMIT ?`)
		stmt.BindBytes(1, startKey)
		stmt.BindInt64(2, int64(chunkSize+1))
	}
	defer stmt.Reset()

	count := 0
	for {
		hasRow, err := stmt.Step()
		if err != nil {
			ReleaseSpanRecords(records) // Return to pool on error
			return nil, nil, nil, false, fmt.Errorf("failed to step: %w", err)
		}
		if !hasRow {
			break
		}

		count++

		// If we've read chunkSize+1, there's more data - don't include this row
		if count > chunkSize {
			break
		}

		// Read key
		keyLen := stmt.ColumnLen(0)
		key := make([]byte, keyLen)
		stmt.ColumnBytes(0, key)

		if firstKey == nil {
			firstKey = key
		}
		lastKey = key

		// Read span data
		dataLen := stmt.ColumnLen(1)
		dataBytes := make([]byte, dataLen)
		stmt.ColumnBytes(1, dataBytes)

		// Unmarshal span data
		spanData, err := UnmarshalSpanData(dataBytes)
		if err != nil {
			slog.Warn("error unmarshaling span data during chunked read, skipping",
				slog.String("key", fmt.Sprintf("%x", key)),
				slog.Any("error", err))
			continue
		}

		// Convert to record and append to pooled slice
		record := ConvertSpanDataToRecord(spanData)
		*records = append(*records, record)
	}

	hasMore := count > chunkSize
	return records, firstKey, lastKey, hasMore, nil
}

