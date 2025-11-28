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

// MetadataKeyUnretrievedCount is the key for storing unretrieved span count
const MetadataKeyUnretrievedCount = "unretrieved_count"

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

// --- SQLite Storage Implementation ---

// Storage provides an interface for interacting with SQLite WAL storage.
type Storage struct {
	pool *sqlitex.Pool
}

// NewStorage initializes a new SQLite database at the specified path.
// It creates the schema, performs initial counter reconciliation, and starts
// a background goroutine for periodic reconciliation.
func NewStorage(path string) (*Storage, error) {
	// Open connection pool with 10 connections
	// URI format enables WAL mode and other pragmas
	uri := fmt.Sprintf("file:%s?_journal_mode=WAL&_busy_timeout=5000&_synchronous=NORMAL", path)
	pool, err := sqlitex.Open(uri, 0, 10)
	if err != nil {
		return nil, fmt.Errorf("failed to open sqlite pool: %w", err)
	}

	slog.Info("sqlite opened", slog.String("path", path))

	storage := &Storage{pool: pool}

	// Initialize schema
	if err := storage.initSchema(); err != nil {
		pool.Close()
		return nil, fmt.Errorf("failed to initialize schema: %w", err)
	}

	// Perform initial reconciliation on startup
	if err := storage.ReconcileCount(); err != nil {
		slog.Warn("Initial counter reconciliation failed", slog.Any("error", err))
	}

	// Start periodic reconciliation (every 60 minutes)
	go func() {
		ticker := time.NewTicker(60 * time.Minute)
		defer ticker.Stop()
		for range ticker.C {
			if err := storage.ReconcileCount(); err != nil {
				slog.Error("Periodic counter reconciliation failed", slog.Any("error", err))
			}
		}
	}()

	return storage, nil
}

// initSchema creates the database tables if they don't exist.
func (s *Storage) initSchema() error {
	conn := s.pool.Get(nil)
	if conn == nil {
		return fmt.Errorf("failed to get connection from pool")
	}
	defer s.pool.Put(conn)

	// Create spans table with ULID as primary key
	// WITHOUT ROWID optimization for BLOB primary keys
	// resource_bytes is nullable - all data is stored in span_bytes as SpanDataContainer
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
	`)
	if err != nil {
		return fmt.Errorf("failed to create schema: %w", err)
	}

	return nil
}

// Close safely closes the SQLite connection pool.
func (s *Storage) Close() error {
	slog.Info("closing sqlite")
	return s.pool.Close()
}

// Sync is a no-op for SQLite WAL mode - writes are already durable.
// Kept for interface compatibility.
func (s *Storage) Sync() error {
	slog.Info("sqlite sync (no-op in WAL mode)")
	return nil
}

// WriteSpan serializes a span and resource and writes them to SQLite.
// The key is a monotonic ULID to ensure chronological order.
// This also atomically increments the unretrieved span counter.
func (s *Storage) WriteSpan(span *tracepb.Span, resource *resourcepb.Resource) error {
	conn := s.pool.Get(nil)
	if conn == nil {
		return fmt.Errorf("failed to get connection from pool")
	}
	defer s.pool.Put(conn)

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
	// span_bytes stores the full SpanDataContainer
	// resource_bytes is left NULL - all data is in span_bytes
	stmt := conn.Prep("INSERT INTO spans (key_ulid, span_bytes) VALUES (?, ?)")
	stmt.BindBytes(1, key[:])
	stmt.BindBytes(2, dataBytes)

	_, err = stmt.Step()
	stmt.Reset()
	if err != nil {
		return fmt.Errorf("failed to insert span: %w", err)
	}

	// Increment counter
	stmt = conn.Prep("UPDATE metadata SET value = value + 1 WHERE key = ?")
	stmt.BindText(1, MetadataKeyUnretrievedCount)
	_, err = stmt.Step()
	stmt.Reset()
	if err != nil {
		return fmt.Errorf("failed to increment counter: %w", err)
	}

	return nil
}

// ReadSpans reads spans from the database starting after startKey.
// It sends each span via the sendFunc callback.
// Returns the last key processed, count of corrupted spans, and any error.
func (s *Storage) ReadSpans(startKey []byte, batchSize uint32, sendFunc func(key, spanBytes, resourceBytes []byte) error) (lastKeyProcessed []byte, corruptedCount uint32, err error) {
	conn := s.pool.Get(nil)
	if conn == nil {
		return nil, 0, fmt.Errorf("failed to get connection from pool")
	}
	defer s.pool.Put(conn)

	var stmt *sqlite.Stmt
	if len(startKey) == 0 {
		stmt = conn.Prep("SELECT key_ulid, span_bytes FROM spans ORDER BY key_ulid LIMIT ?")
		stmt.BindInt64(1, int64(batchSize))
	} else {
		stmt = conn.Prep("SELECT key_ulid, span_bytes FROM spans WHERE key_ulid > ? ORDER BY key_ulid LIMIT ?")
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

// --- Counter Operations ---

// GetUnretrievedCount returns the current unretrieved span count.
func (s *Storage) GetUnretrievedCount() (uint64, error) {
	conn := s.pool.Get(nil)
	if conn == nil {
		return 0, fmt.Errorf("failed to get connection from pool")
	}
	defer s.pool.Put(conn)

	stmt := conn.Prep("SELECT value FROM metadata WHERE key = ?")
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
func (s *Storage) DecrementAndGetCount(n uint32) (uint64, error) {
	conn := s.pool.Get(nil)
	if conn == nil {
		return 0, fmt.Errorf("failed to get connection from pool")
	}
	defer s.pool.Put(conn)

	var remaining uint64
	var err error
	defer sqlitex.Save(conn)(&err)

	// Get current count
	stmt := conn.Prep("SELECT value FROM metadata WHERE key = ?")
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
	stmt = conn.Prep("UPDATE metadata SET value = ? WHERE key = ?")
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
func (s *Storage) ReconcileCount() error {
	conn := s.pool.Get(nil)
	if conn == nil {
		return fmt.Errorf("failed to get connection from pool")
	}
	defer s.pool.Put(conn)

	// Count actual spans
	stmt := conn.Prep("SELECT COUNT(*) FROM spans")
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
	storedCount, err := s.GetUnretrievedCount()
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
		stmt = conn.Prep("UPDATE metadata SET value = ? WHERE key = ?")
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
