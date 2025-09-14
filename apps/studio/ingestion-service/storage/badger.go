package storage

import (
	"crypto/rand"
	"log"
	"sync"
	"time"

	badger "github.com/dgraph-io/badger/v4"
	"github.com/oklog/ulid/v2"
	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
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

// WriteSpan serializes a SpanData struct and writes it to BadgerDB.
// The key is a monotonic ULID to ensure chronological order and prevent collisions.
func (s *Storage) WriteSpan(span *tracepb.Span, resource *resourcepb.Resource) error {
	// Create a SpanData struct
	spanData := &SpanData{
		Span:     span,
		Resource: resource,
	}

	// Serialize the SpanData to a byte slice
	dataBytes, err := MarshalSpanData(spanData)
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
		return txn.Set(key[:], dataBytes)
	})
}

// ReadSpans iterates through the database and sends key-value pairs to the provided channel.
// It uses prefetching to optimize for sequential reads.
func (s *Storage) ReadSpans(startKey []byte, batchSize uint32, sendFunc func(key, spanBytes, resourceBytes []byte) error) error {
	return s.db.View(func(txn *badger.Txn) error {
		// Enable prefetching for faster iteration. The default prefetch size is 100.
		opts := badger.DefaultIteratorOptions
		opts.PrefetchValues = true

		it := txn.NewIterator(opts)
		defer it.Close()

		// If startKey is nil, we start from the beginning. Otherwise, we seek to the key *after* the provided one.
		// This prevents re-reading the last processed span.
		if len(startKey) == 0 {
			it.Rewind()
		} else {
			// To seek to the *next* key, we append a zero byte to the startKey.
			// This works because keys are sorted lexicographically.
			it.Seek(append(startKey, 0))
		}

		var count uint32
		for it.Valid() && count < batchSize {
			item := it.Item()
			key := item.Key()

			// ValueCopy is used here because we need to send the value over the stream.
			// The callback-based Value() is more for cases where the value might be discarded.
			val, err := item.ValueCopy(nil)
			if err != nil {
				return err
			}

			// Unmarshal the value to SpanData
			spanData, err := UnmarshalSpanData(val)
			if err != nil {
				log.Printf("Error unmarshaling span data: %v", err)
				// Skip corrupted data
				count++
				it.Next()
				continue
			}

			// Marshal the span and resource back to bytes for sending
			spanBytes, err := proto.Marshal(spanData.Span)
			if err != nil {
				log.Printf("Error marshaling span: %v", err)
				count++
				it.Next()
				continue
			}
			resourceBytes, err := proto.Marshal(spanData.Resource)
			if err != nil {
				log.Printf("Error marshaling resource: %v", err)
				count++
				it.Next()
				continue
			}

			// The sendFunc sends the key and the span/resource bytes to the client stream.
			if err := sendFunc(key, spanBytes, resourceBytes); err != nil {
				return err // Propagate error from the send function (e.g., client disconnected)
			}

			count++
			it.Next()
		}
		return nil
	})
}
