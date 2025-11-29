"""Background indexer for Parquet files.

This module implements an async infinite loop that:
1. Polls filesystem for new Parquet files
2. Filters out already-indexed files (via DuckDB parquet_files)
3. Reads span metadata from new files
4. Indexes metadata into DuckDB

Replaces: span_ingestion_poller (gRPC-based) for V4 architecture.
"""

import asyncio

from loguru import logger

from app.config.settings import settings
from app.db_duckdb import v4_repository
from app.features.parquet_indexer.file_scanner import scan_parquet_files
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata


async def parquet_indexer() -> None:
    """Background task that indexes Parquet files into DuckDB.

    This is an infinite async loop that:
    1. Scans span storage path for .parquet files
    2. Filters out files already in parquet_files table (deduplication)
    3. For each new file (up to batch_size per cycle):
       - Reads span metadata from Parquet
       - Indexes metadata into DuckDB (parquet_files + span_metadata + services)
    4. Handles errors gracefully (logs bad files, continues)
    5. Supports graceful shutdown (cancellation)

    Error Handling:
        - Missing storage path: Log and continue (Go might not have flushed yet)
        - Bad Parquet file: Log with full context (path, error), skip, continue
        - DuckDB errors: Log and continue (retry on next cycle)
    """
    logger.info(
        "Starting parquet indexer",
        extra={
            "span_storage_path": settings.parquet_indexer.span_storage_path_resolved,
            "poll_interval": settings.parquet_indexer.poll_interval,
            "batch_size": settings.parquet_indexer.batch_size,
        },
    )

    try:
        while True:
            # Sleep first (poll interval)
            await asyncio.sleep(settings.parquet_indexer.poll_interval)

            try:
                await index_new_files()
            except Exception as e:
                logger.error(
                    "Error in indexer cycle",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                # Continue polling on error

    except asyncio.CancelledError:
        logger.info("Parquet indexer cancelled, shutting down")
        raise

    finally:
        logger.info("Parquet indexer stopped")


async def index_new_files() -> int:
    """Scan for and index new Parquet files.

    This is the core indexing logic, extracted for testability.

    Returns:
        Number of files successfully indexed in this cycle.
    """
    # Run filesystem scan in thread pool (blocking I/O)
    loop = asyncio.get_event_loop()
    all_files = await loop.run_in_executor(
        None, scan_parquet_files, settings.parquet_indexer.span_storage_path_resolved
    )

    if not all_files:
        logger.debug("No parquet files found in storage path")
        return 0

    # Get already-indexed paths from DuckDB (deduplication checkpoint)
    indexed_paths = await loop.run_in_executor(None, v4_repository.get_indexed_file_paths)

    # Get failed file paths to skip (don't retry known bad files)
    failed_paths = await loop.run_in_executor(None, v4_repository.get_failed_file_paths)

    # Filter to unindexed files only (exclude both indexed and failed)
    skip_paths = indexed_paths | failed_paths
    new_files = [f for f in all_files if f.path not in skip_paths]

    if not new_files:
        logger.debug(f"All {len(all_files)} parquet files already indexed")
        return 0

    logger.info(
        f"Found {len(new_files)} new parquet files to index",
        extra={
            "total_files": len(all_files),
            "already_indexed": len(indexed_paths),
            "new_files": len(new_files),
        },
    )

    # Process up to batch_size files per cycle
    batch = new_files[: settings.parquet_indexer.batch_size]
    indexed_count = 0

    for file_info in batch:
        try:
            # Read metadata from Parquet (blocking I/O)
            file_data = await loop.run_in_executor(
                None, read_parquet_metadata, file_info.path, file_info.size_bytes
            )

            # Index into DuckDB (blocking I/O)
            span_count = await loop.run_in_executor(
                None, v4_repository.index_parquet_file, file_data
            )

            indexed_count += 1
            logger.debug(
                f"Indexed file {indexed_count}/{len(batch)}",
                extra={
                    "file_path": file_info.path,
                    "span_count": span_count,
                    "service": file_data.service_name,
                },
            )

        except Exception as e:
            # Log bad files with full context, record to DB, skip, continue
            error_type = type(e).__name__
            error_message = str(e)

            logger.error(
                "Failed to index parquet file",
                extra={
                    "file_path": file_info.path,
                    "file_size": file_info.size_bytes,
                    "error": error_message,
                    "error_type": error_type,
                },
            )

            # Record failure to DB so we don't retry on next poll
            try:
                await loop.run_in_executor(
                    None,
                    v4_repository.record_failed_file,
                    file_info.path,
                    error_type,
                    error_message,
                    file_info.size_bytes,
                )
            except Exception as record_err:
                logger.warning(
                    f"Failed to record failed file to DB: {record_err}",
                    extra={"file_path": file_info.path},
                )

            continue

    if indexed_count > 0:
        remaining = len(new_files) - len(batch)
        logger.info(
            f"Indexed {indexed_count}/{len(batch)} files successfully",
            extra={
                "indexed": indexed_count,
                "attempted": len(batch),
                "remaining": remaining,
            },
        )

    return indexed_count
