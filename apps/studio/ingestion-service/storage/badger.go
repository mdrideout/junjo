package storage

import (
	"crypto/rand"
	"log"
	"sync"
	"time"

	badger "github.com/dgraph-io/badger/v4"
	"github.com/oklog/ulid/v2"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/proto"
)

// --- Monotonic ULID Generator ---

var (
	// ulidGenerator is a single, shared monotonic entropy source protected by a mutex.
	// This ensures that even if multiple goroutines call for a new ID in the same
	// millisecond, each call will produce a unique and strictly increasing ULID.
	ulidGenerator = struct {
		sync.Mutex
		*ulid.MonotonicEntropy
	}{
		// We pass crypto/rand.Reader as the initial entropy source, and 0 for the increment.
		MonotonicEntropy: ulid.Monotonic(rand.Reader, 0),
	}
)

// newULID generates a new, monotonic ULID in a thread-safe manner.
func newULID() (ulid.ULID, error) {
	ulidGenerator.Lock()
	defer ulidGenerator.Unlock()

	// ulid.New requires the time in milliseconds and an entropy source.
	// We provide the current time and our locked monotonic entropy source.
	// The MonotonicEntropy will ensure the random part of the ULID is incremented
	// if we are in the same millisecond as the previous call.
	return ulid.New(ulid.Timestamp(time.Now()), &ulidGenerator)
}

// --- Storage Implementation ---

// Storage provides an interface for interacting with the BadgerDB instance.
type Storage struct {
	db *badger.DB
}

// NewStorage initializes a new BadgerDB instance at the specified path.
func NewStorage(path string) (*Storage, error) {
	opts := badger.DefaultOptions(path)
	db, err := badger.Open(opts)
	if err != nil {
		return nil, err
	}
	log.Printf("BadgerDB opened successfully at path: %s", path)
	return &Storage{db: db}, nil
}

// Close safely closes the BadgerDB connection.
func (s *Storage) Close() error {
	log.Println("Closing BadgerDB...")
	return s.db.Close()
}

// Sync flushes all pending writes to disk.
func (s *Storage) Sync() error {
	log.Println("Syncing BadgerDB to disk...")
	return s.db.Sync()
}

// WriteSpan serializes a protobuf span and writes it to BadgerDB.
// The key is a monotonic ULID to ensure chronological order and prevent collisions.
func (s *Storage) WriteSpan(span *tracepb.Span) error {
	// Serialize the span to a byte slice
	spanBytes, err := proto.Marshal(span)
	if err != nil {
		return err
	}

	// Generate a new monotonic ULID for the key.
	key, err := newULID()
	if err != nil {
		return err
	}

	// Perform the write within a transaction
	return s.db.Update(func(txn *badger.Txn) error {
		// The key is the binary representation of the ULID.
		return txn.Set(key[:], spanBytes)
	})
}
