"""Filesystem scanner for Parquet files.

Walks the span storage directory tree to discover Parquet files
written by Go ingestion service.

Expected directory structure (from Go flusher):
    {base_path}/year=YYYY/month=MM/day=DD/{service}_{timestamp}_{uuid8}.parquet
"""

from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass(frozen=True)
class ParquetFileInfo:
    """Information about a discovered Parquet file."""

    path: str
    size_bytes: int
    mtime: float  # Unix timestamp of last modification


def scan_parquet_files(base_path: str) -> list[ParquetFileInfo]:
    """Scan directory tree for Parquet files.

    Args:
        base_path: Root directory to scan (e.g., /app/.dbdata/parquet)

    Returns:
        List of ParquetFileInfo for all .parquet files found.
        Returns empty list if base_path doesn't exist.

    Note:
        Files are returned in no particular order. The indexer
        should handle deduplication via DuckDB parquet_files table.
    """
    base = Path(base_path)

    if not base.exists():
        logger.debug(f"Span storage path does not exist yet: {base_path}")
        return []

    if not base.is_dir():
        logger.warning(f"Span storage path is not a directory: {base_path}")
        return []

    files: list[ParquetFileInfo] = []

    # Walk directory tree looking for .parquet files
    # Pattern: year=*/month=*/day=*/*.parquet
    for parquet_path in base.rglob("*.parquet"):
        try:
            stat = parquet_path.stat()
            files.append(
                ParquetFileInfo(
                    path=str(parquet_path),
                    size_bytes=stat.st_size,
                    mtime=stat.st_mtime,
                )
            )
        except OSError as e:
            # File might have been deleted between rglob and stat
            logger.warning(f"Could not stat file {parquet_path}: {e}")
            continue

    logger.debug(f"Found {len(files)} parquet files in {base_path}")
    return files
