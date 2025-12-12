package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"time"
)

var (
	cfg     *Config
	cfgOnce sync.Once
	cfgErr  error
)

// Get returns the global config, loading it on first call.
// Panics if config loading fails.
func Get() *Config {
	// If config was set via SetForTesting, return it directly
	if cfg != nil {
		return cfg
	}
	cfgOnce.Do(func() {
		cfg, cfgErr = Load()
	})
	if cfgErr != nil {
		panic(fmt.Sprintf("failed to load config: %v", cfgErr))
	}
	return cfg
}

// MustLoad loads config and panics on error. Call once at startup.
func MustLoad() {
	_ = Get()
}

// SetForTesting sets a custom config for testing purposes.
// This bypasses the sync.Once and allows tests to configure the global config.
// Only use in tests.
func SetForTesting(c *Config) {
	cfg = c
	cfgErr = nil
	// Note: We don't reset cfgOnce because tests may call this multiple times.
	// The direct assignment to cfg works because Get() checks cfg after cfgOnce.Do().
}

// Config holds all configuration for the ingestion service.
type Config struct {
	SQLite  SQLiteConfig
	Flusher FlusherConfig
	Server  ServerConfig
	Backend BackendConfig
	Log     LogConfig
}

// SQLiteConfig holds SQLite database configuration.
type SQLiteConfig struct {
	Path string
}

// FlusherConfig holds configuration for the Parquet flusher.
type FlusherConfig struct {
	OutputDir          string
	Interval           time.Duration
	MaxAge             time.Duration
	MaxRows            int64
	MinRows            int64
	MaxBytes           int64 // Maximum WAL size before triggering cold flush (default 50MB)
	WarmSnapshotBytes  int64 // Minimum bytes before triggering warm snapshot (default 10MB)
	FlushChunkSize     int   // Number of spans per chunk during streaming flush (default 50000)
}

// ServerConfig holds gRPC server configuration.
type ServerConfig struct {
	PublicPort              string
	InternalPort            string
	BackpressureMaxBytes    int64 // Max span data bytes before applying backpressure (default 200MB)
	BackpressureCheckInterval int  // Seconds between backpressure checks (default 2)
}

// BackendConfig holds backend service connection configuration.
type BackendConfig struct {
	Host string
	Port string
}

// LogConfig holds logging configuration.
type LogConfig struct {
	Level  string
	Format string
}

// Default returns a Config with all default values.
func Default() *Config {
	homeDir, _ := os.UserHomeDir()

	return &Config{
		SQLite: SQLiteConfig{
			Path: filepath.Join(homeDir, ".junjo", "ingestion-wal", "spans.db"),
		},
		Flusher: FlusherConfig{
			OutputDir:         filepath.Join(homeDir, ".junjo", "spans"),
			Interval:          15 * time.Second, // Check every 15s for flush conditions
			MaxAge:            1 * time.Hour,
			MaxRows:           100000,
			MinRows:           1000,
			MaxBytes:          50 * 1024 * 1024,  // 50MB
			WarmSnapshotBytes: 10 * 1024 * 1024,  // 10MB
			FlushChunkSize:    5000,              // 5K spans per chunk (~10MB memory)
		},
		Server: ServerConfig{
			PublicPort:                "50051",
			InternalPort:              "50052",
			BackpressureMaxBytes:      100 * 1024 * 1024, // 100MB
			BackpressureCheckInterval: 2,                  // 2 seconds
		},
		Backend: BackendConfig{
			Host: "junjo-ai-studio-backend",
			Port: "50053",
		},
		Log: LogConfig{
			Level:  "info",
			Format: "json",
		},
	}
}

// Load reads configuration from environment variables.
// Returns an error for invalid values.
func Load() (*Config, error) {
	cfg := Default()

	// SQLite configuration
	if path := os.Getenv("JUNJO_WAL_SQLITE_PATH"); path != "" {
		cfg.SQLite.Path = path
	}

	// Flusher configuration
	if path := os.Getenv("PARQUET_STORAGE_PATH"); path != "" {
		cfg.Flusher.OutputDir = path
	}

	if interval := os.Getenv("FLUSH_INTERVAL"); interval != "" {
		d, err := time.ParseDuration(interval)
		if err != nil {
			return nil, fmt.Errorf("invalid FLUSH_INTERVAL %q: %w", interval, err)
		}
		cfg.Flusher.Interval = d
	}

	if maxAge := os.Getenv("FLUSH_MAX_AGE"); maxAge != "" {
		d, err := time.ParseDuration(maxAge)
		if err != nil {
			return nil, fmt.Errorf("invalid FLUSH_MAX_AGE %q: %w", maxAge, err)
		}
		cfg.Flusher.MaxAge = d
	}

	if maxRows := os.Getenv("FLUSH_MAX_ROWS"); maxRows != "" {
		n, err := strconv.ParseInt(maxRows, 10, 64)
		if err != nil {
			return nil, fmt.Errorf("invalid FLUSH_MAX_ROWS %q: %w", maxRows, err)
		}
		cfg.Flusher.MaxRows = n
	}

	if minRows := os.Getenv("FLUSH_MIN_ROWS"); minRows != "" {
		n, err := strconv.ParseInt(minRows, 10, 64)
		if err != nil {
			return nil, fmt.Errorf("invalid FLUSH_MIN_ROWS %q: %w", minRows, err)
		}
		cfg.Flusher.MinRows = n
	}

	if maxBytes := os.Getenv("FLUSH_MAX_BYTES"); maxBytes != "" {
		n, err := strconv.ParseInt(maxBytes, 10, 64)
		if err != nil {
			return nil, fmt.Errorf("invalid FLUSH_MAX_BYTES %q: %w", maxBytes, err)
		}
		cfg.Flusher.MaxBytes = n
	}

	if warmBytes := os.Getenv("WARM_SNAPSHOT_BYTES"); warmBytes != "" {
		n, err := strconv.ParseInt(warmBytes, 10, 64)
		if err != nil {
			return nil, fmt.Errorf("invalid WARM_SNAPSHOT_BYTES %q: %w", warmBytes, err)
		}
		cfg.Flusher.WarmSnapshotBytes = n
	}

	if chunkSize := os.Getenv("FLUSH_CHUNK_SIZE"); chunkSize != "" {
		n, err := strconv.Atoi(chunkSize)
		if err != nil {
			return nil, fmt.Errorf("invalid FLUSH_CHUNK_SIZE %q: %w", chunkSize, err)
		}
		cfg.Flusher.FlushChunkSize = n
	}

	// Server configuration
	if port := os.Getenv("GRPC_PORT"); port != "" {
		cfg.Server.PublicPort = port
	}

	if port := os.Getenv("INTERNAL_GRPC_PORT"); port != "" {
		cfg.Server.InternalPort = port
	}

	if maxBytes := os.Getenv("BACKPRESSURE_MAX_BYTES"); maxBytes != "" {
		n, err := strconv.ParseInt(maxBytes, 10, 64)
		if err != nil {
			return nil, fmt.Errorf("invalid BACKPRESSURE_MAX_BYTES %q: %w", maxBytes, err)
		}
		cfg.Server.BackpressureMaxBytes = n
	}

	if interval := os.Getenv("BACKPRESSURE_CHECK_INTERVAL"); interval != "" {
		n, err := strconv.Atoi(interval)
		if err != nil {
			return nil, fmt.Errorf("invalid BACKPRESSURE_CHECK_INTERVAL %q: %w", interval, err)
		}
		cfg.Server.BackpressureCheckInterval = n
	}

	// Backend configuration
	if host := os.Getenv("BACKEND_GRPC_HOST"); host != "" {
		cfg.Backend.Host = host
	}

	if port := os.Getenv("BACKEND_GRPC_PORT"); port != "" {
		cfg.Backend.Port = port
	}

	// Log configuration
	if level := os.Getenv("JUNJO_LOG_LEVEL"); level != "" {
		cfg.Log.Level = level
	}

	if format := os.Getenv("JUNJO_LOG_FORMAT"); format != "" {
		cfg.Log.Format = format
	}

	return cfg, nil
}
