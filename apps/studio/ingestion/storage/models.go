package storage

import (
	"time"
)

// MetadataKeyUnretrievedCount is the key for storing unretrieved span count.
const MetadataKeyUnretrievedCount = "unretrieved_count"

// FlushState represents the current state of the flush process.
type FlushState struct {
	LastFlushTime    time.Time
	FirstFlushedKey  []byte
	LastFlushedKey   []byte
	TotalFlushedRows int64
}
