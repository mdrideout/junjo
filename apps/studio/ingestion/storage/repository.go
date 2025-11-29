package storage

import (
	"crypto/rand"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"crawshaw.io/sqlite"
	"crawshaw.io/sqlite/sqlitex"
	"github.com/oklog/ulid/v2"
	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/proto"
)

// SpanRepository defines the data access interface for span storage.
type SpanRepository interface {
	// Span operations
	WriteSpan(span *tracepb.Span, resource *resourcepb.Resource) error
	ReadSpans(startKey []byte, batchSize uint32, sendFunc func(key, spanBytes, resourceBytes []byte) error) (lastKeyProcessed []byte, corruptedCount uint32, err error)
	DeleteSpansInRange(firstKey, lastKey []byte) error
	GetSpanCount() (int64, error)
	ReadAllSpansForFlush() (records []SpanRecord, firstKey, lastKey []byte, err error)

	// Counter operations
	GetUnretrievedCount() (uint64, error)
	DecrementAndGetCount(n uint32) (uint64, error)
	ReconcileCount() error

	// Flush state
	GetFlushState() (*FlushState, error)
	UpdateFlushState(firstKey, lastKey []byte, rowsFlushed int64) error

	// Lifecycle
	Sync() error
	Close() error
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

// --- SQLiteRepository Implementation ---

// SQLiteRepository implements SpanRepository using SQLite.
type SQLiteRepository struct {
	pool *sqlitex.Pool
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

	repo := &SQLiteRepository{pool: pool}

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
			resource_bytes BLOB
		) WITHOUT ROWID;

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

	// Begin transaction
	defer sqlitex.Save(conn)(&err)

	// Insert span
	stmt := conn.Prep(`INSERT INTO spans (key_ulid, span_bytes) VALUES (?, ?)`)
	stmt.BindBytes(1, key[:])
	stmt.BindBytes(2, dataBytes)

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

	state := &FlushState{
		LastFlushTime:    time.Unix(stmt.ColumnInt64(0), 0).UTC(),
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
