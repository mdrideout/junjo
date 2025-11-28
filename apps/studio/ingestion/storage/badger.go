package storage

import (
	"bytes"
	"crypto/rand"
	"encoding/binary"
	"log/slog"
	"sync"
	"time"

	badger "github.com/dgraph-io/badger/v4"
	"github.com/oklog/ulid/v2"
	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/proto"
)

// CounterKey is the special key used to store the unretrieved span count
const CounterKey = "__span_count__"

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
// It also performs an initial counter reconciliation and starts a background
// goroutine to periodically reconcile the counter.
func NewStorage(path string) (*Storage, error) {
	opts := badger.DefaultOptions(path)
	db, err := badger.Open(opts)
	if err != nil {
		return nil, err
	}
	slog.Info("badgerdb opened", slog.String("path", path))

	storage := &Storage{db: db}

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

// Close safely closes the BadgerDB connection.
func (s *Storage) Close() error {
	slog.Info("closing badgerdb")
	return s.db.Close()
}

// Sync flushes all pending writes to disk.
func (s *Storage) Sync() error {
	slog.Info("syncing badgerdb to disk")
	return s.db.Sync()
}

// WriteSpan serializes a SpanData struct and writes it to BadgerDB.
// The key is a monotonic ULID to ensure chronological order and prevent collisions.
// This also atomically increments the unretrieved span counter.
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
		// Write the span
		if err := txn.Set(key[:], dataBytes); err != nil {
			return err
		}
		// Increment the counter atomically
		return s.incrementCounterInTxn(txn, 1)
	})
}

// ReadSpans iterates through the database and sends key-value pairs to the provided channel.
// It uses prefetching to optimize for sequential reads.
// Returns the last key processed (even if corrupted), corrupted span count, and any error.
func (s *Storage) ReadSpans(startKey []byte, batchSize uint32, sendFunc func(key, spanBytes, resourceBytes []byte) error) (lastKeyProcessed []byte, corruptedCount uint32, err error) {
	err = s.db.View(func(txn *badger.Txn) error {
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

			// Skip internal counter key - it's not a span
			if bytes.Equal(key, []byte(CounterKey)) {
				it.Next()
				continue
			}

			// Track the last key we process (even if corrupted)
			// Make a copy because the key slice is reused by BadgerDB
			lastKeyProcessed = append([]byte(nil), key...)

			// ValueCopy is used here because we need to send the value over the stream.
			// The callback-based Value() is more for cases where the value might be discarded.
			val, err := item.ValueCopy(nil)
			if err != nil {
				return err
			}

			// Unmarshal the value to SpanData
			spanData, err := UnmarshalSpanData(val)
			if err != nil {
				slog.Warn("error unmarshaling span data",
					slog.String("key", string(key)),
					slog.Any("error", err))
				// Skip corrupted data
				corruptedCount++
				count++
				it.Next()
				continue
			}

			// Marshal the span and resource back to bytes for sending
			spanBytes, err := proto.Marshal(spanData.Span)
			if err != nil {
				slog.Warn("error marshaling span",
					slog.String("key", string(key)),
					slog.Any("error", err))
				corruptedCount++
				count++
				it.Next()
				continue
			}
			resourceBytes, err := proto.Marshal(spanData.Resource)
			if err != nil {
				slog.Warn("error marshaling resource",
					slog.String("key", string(key)),
					slog.Any("error", err))
				corruptedCount++
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
	return lastKeyProcessed, corruptedCount, err
}

// --- Counter Operations ---

// incrementCounterInTxn increments the span counter by the specified delta within an existing transaction.
func (s *Storage) incrementCounterInTxn(txn *badger.Txn, delta uint64) error {
	item, err := txn.Get([]byte(CounterKey))
	var count uint64
	if err == badger.ErrKeyNotFound {
		count = 0
	} else if err != nil {
		return err
	} else {
		err = item.Value(func(val []byte) error {
			count = binary.BigEndian.Uint64(val)
			return nil
		})
		if err != nil {
			return err
		}
	}

	count += delta
	buf := make([]byte, 8)
	binary.BigEndian.PutUint64(buf, count)
	return txn.Set([]byte(CounterKey), buf)
}

// GetUnretrievedCount returns the current unretrieved span count.
func (s *Storage) GetUnretrievedCount() (uint64, error) {
	var count uint64
	err := s.db.View(func(txn *badger.Txn) error {
		item, err := txn.Get([]byte(CounterKey))
		if err == badger.ErrKeyNotFound {
			return nil // Count is 0
		}
		if err != nil {
			return err
		}
		return item.Value(func(val []byte) error {
			count = binary.BigEndian.Uint64(val)
			return nil
		})
	})
	return count, err
}

// DecrementAndGetCount decrements the span counter by the specified amount and returns the remaining count.
// This is called after a batch of spans has been successfully read.
func (s *Storage) DecrementAndGetCount(n uint32) (uint64, error) {
	var remaining uint64
	err := s.db.Update(func(txn *badger.Txn) error {
		// Get current count
		item, err := txn.Get([]byte(CounterKey))
		if err == badger.ErrKeyNotFound {
			// Counter doesn't exist yet, nothing to decrement
			remaining = 0
			return nil
		}
		if err != nil {
			return err
		}

		var count uint64
		err = item.Value(func(val []byte) error {
			count = binary.BigEndian.Uint64(val)
			return nil
		})
		if err != nil {
			return err
		}

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

		// Write back
		buf := make([]byte, 8)
		binary.BigEndian.PutUint64(buf, count)
		return txn.Set([]byte(CounterKey), buf)
	})
	return remaining, err
}

// ReconcileCount performs reconciliation by counting actual spans in the database
// and correcting the counter if drift is detected.
func (s *Storage) ReconcileCount() error {
	// Count actual spans (excluding the counter key)
	actualCount := uint64(0)
	err := s.db.View(func(txn *badger.Txn) error {
		opts := badger.DefaultIteratorOptions
		opts.PrefetchValues = false // Only need keys for counting
		it := txn.NewIterator(opts)
		defer it.Close()

		for it.Rewind(); it.Valid(); it.Next() {
			key := it.Item().Key()
			if !bytes.Equal(key, []byte(CounterKey)) {
				actualCount++
			}
		}
		return nil
	})
	if err != nil {
		return err
	}

	// Get stored counter
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
		return s.db.Update(func(txn *badger.Txn) error {
			buf := make([]byte, 8)
			binary.BigEndian.PutUint64(buf, actualCount)
			return txn.Set([]byte(CounterKey), buf)
		})
	}

	slog.Info("Counter reconciliation completed, no drift detected",
		slog.Uint64("count", actualCount))
	return nil
}
