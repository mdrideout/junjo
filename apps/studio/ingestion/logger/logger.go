package logger

import (
	"log/slog"
	"os"
	"strings"

	"junjo-ai-studio/ingestion/config"
)

// Init initializes the global slog logger from config.
// Call once at startup before any logging.
func Init() {
	cfg := config.Get().Log
	level := parseLogLevel(cfg.Level)

	// Create handler based on format
	var handler slog.Handler
	opts := &slog.HandlerOptions{
		Level:     level,
		AddSource: level == slog.LevelDebug, // Add source location for debug
	}

	if cfg.Format == "json" {
		handler = slog.NewJSONHandler(os.Stdout, opts)
	} else {
		handler = slog.NewTextHandler(os.Stdout, opts)
	}

	slog.SetDefault(slog.New(handler))
}

// parseLogLevel converts a string log level to slog.Level.
// Supports: debug, info, warn/warning, error
// Default: info
func parseLogLevel(level string) slog.Level {
	switch strings.ToLower(level) {
	case "debug":
		return slog.LevelDebug
	case "warn", "warning":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}
