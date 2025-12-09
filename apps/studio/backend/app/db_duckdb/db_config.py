"""DuckDB configuration for OTEL span storage.

DuckDB is used for analytics-optimized storage of OpenTelemetry spans.
Unlike SQLite, DuckDB excels at analytical queries on large datasets.

Connection Pattern:
- Use raw duckdb connections for batch inserts (performance)
- Path: /dbdata/duckdb/traces.duckdb (from env)
- Each operation creates its own connection (DuckDB handles concurrency well)

Note: We use raw DuckDB connections instead of SQLAlchemy for performance.
Batch inserts are much faster with duckdb.executemany() than SQLAlchemy ORM.
"""

from contextlib import contextmanager
from pathlib import Path

import duckdb
from loguru import logger

from app.config.settings import settings


@contextmanager
def get_connection():
    """Get a DuckDB connection with automatic cleanup.

    This is a context manager that ensures the connection is properly closed
    after use, following DuckDB Python best practices.

    Usage:
        with get_connection() as conn:
            conn.execute("SELECT 1")

    Yields:
        DuckDB connection to the spans database (automatically closed on exit).

    Note:
        DuckDB handles concurrent reads/writes well (MVCC), so creating
        connections per-operation is acceptable for asyncio (single-threaded).
    """
    # Ensure parent directory exists before connecting
    db_path = Path(settings.database.duckdb_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()


def initialize_tables():
    """Initialize DuckDB tables and indexes.

    V4 Architecture: Creates parquet_files, span_metadata, and services tables.
    These tables store metadata for Parquet files written by Go ingestion.
    Full span data (attributes, events) stays in Parquet files.

    Should be called on application startup.

    This is a synchronous function since it runs during app startup
    before the event loop is fully active.
    """
    with get_connection() as conn:
        try:
            schema_dir = Path(__file__).parent / "schemas"

            # V4 Schema: Parquet file registry and span metadata
            # These tables index metadata from Parquet files for fast listing queries
            v4_parquet_files = (schema_dir / "v4_parquet_files.sql").read_text()
            v4_span_metadata = (schema_dir / "v4_span_metadata.sql").read_text()
            v4_file_services = (schema_dir / "v4_file_services.sql").read_text()
            v4_failed_files = (schema_dir / "v4_failed_files.sql").read_text()

            conn.execute(v4_parquet_files)
            conn.execute(v4_span_metadata)
            conn.execute(v4_file_services)
            conn.execute(v4_failed_files)

            logger.info(f"DuckDB V4 tables initialized: {settings.database.duckdb_path}")

        except Exception as e:
            logger.error(f"Failed to initialize DuckDB tables: {e}")
            raise
