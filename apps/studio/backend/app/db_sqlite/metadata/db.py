"""SQLite metadata database connection management.

Thread-safe connection management with WAL mode for concurrent reads/writes.

Key features:
- Thread-local connections for safety
- WAL mode for non-blocking writes
- Configurable page cache (10 MB default)
- Foreign keys enabled for CASCADE deletes

Memory budget:
- Page cache: 10 MB
- Statement cache: < 1 MB
- WAL buffers: ~1 MB
- Total: ~12 MB
"""

import sqlite3
import threading
from pathlib import Path

from loguru import logger

# Thread-local storage for connections
_local = threading.local()

# Global database path (set during init)
_db_path: str | None = None


def init_metadata_db(db_path: str) -> None:
    """Initialize the metadata database.

    Creates the database file and tables if they don't exist.
    Must be called once at application startup.

    Args:
        db_path: Absolute path to the metadata.db file
    """
    global _db_path
    _db_path = db_path

    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Create tables
    conn = _create_connection(db_path)
    try:
        _apply_schema(conn)
        conn.commit()
        logger.info(f"Metadata database initialized: {db_path}")
    finally:
        conn.close()


def _create_connection(db_path: str) -> sqlite3.Connection:
    """Create a new SQLite connection with proper settings.

    Args:
        db_path: Path to the database file

    Returns:
        Configured SQLite connection
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)

    # Apply PRAGMA settings for performance and safety
    conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
    conn.execute("PRAGMA synchronous=NORMAL")  # Safe with WAL
    conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s on SQLITE_BUSY
    conn.execute("PRAGMA cache_size=-10000")  # 10 MB page cache
    conn.execute("PRAGMA temp_store=MEMORY")  # Temp tables in RAM
    conn.execute("PRAGMA mmap_size=52428800")  # 50 MB memory-mapped I/O
    conn.execute("PRAGMA foreign_keys=ON")  # Enable CASCADE deletes

    return conn


def _apply_schema(conn: sqlite3.Connection) -> None:
    """Apply the schema to the database.

    Reads schema.sql and executes all statements.

    Args:
        conn: Active SQLite connection
    """
    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text()

    # Execute all statements
    conn.executescript(schema_sql)


def get_connection() -> sqlite3.Connection:
    """Get a thread-local database connection.

    Each thread gets its own connection, stored in thread-local storage.
    Connections are reused within a thread for efficiency.

    Returns:
        SQLite connection for the current thread

    Raises:
        RuntimeError: If database not initialized
    """
    if _db_path is None:
        raise RuntimeError("Metadata database not initialized. Call init_metadata_db() first.")

    # Check if we have a connection for this thread
    if not hasattr(_local, "connection") or _local.connection is None:
        _local.connection = _create_connection(_db_path)

    return _local.connection


def close_connection() -> None:
    """Close the connection for the current thread.

    Should be called when a thread is done with database operations,
    e.g., during thread pool cleanup.
    """
    if hasattr(_local, "connection") and _local.connection is not None:
        try:
            _local.connection.close()
        except Exception:
            pass
        _local.connection = None


def checkpoint_wal() -> None:
    """Force a WAL checkpoint to write changes to main database file.

    Should be called on application shutdown to ensure durability.
    """
    if _db_path is None:
        return

    conn = get_connection()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        logger.info("Metadata WAL checkpoint complete")
    except Exception as e:
        logger.warning(f"WAL checkpoint failed: {e}")
