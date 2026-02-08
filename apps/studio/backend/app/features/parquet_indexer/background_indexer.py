"""Background indexer for Parquet files.

This module implements an async infinite loop that:
1. Polls filesystem for new Parquet files
2. Filters out already-indexed files (via SQLite metadata)
3. Reads span metadata from new files
4. Indexes metadata into SQLite

Migration Complete:
- The legacy per-span metadata index is removed; SQLite is the sole metadata index
- 10-20x memory reduction achieved

Replaces: span_ingestion_poller (gRPC-based) for V4 architecture.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from loguru import logger

from app.config.settings import settings
from app.db_sqlite.metadata import indexer as sqlite_indexer
from app.db_sqlite.metadata import repository as sqlite_repository
from app.features.parquet_indexer.file_scanner import scan_parquet_files
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata

_index_lock: asyncio.Lock | None = None


def _get_index_lock() -> asyncio.Lock:
    global _index_lock
    if _index_lock is None:
        _index_lock = asyncio.Lock()
    return _index_lock


async def parquet_indexer() -> None:
    """Background task that indexes Parquet files into SQLite metadata.

    This is an infinite async loop that:
    1. Scans span storage path for .parquet files
    2. Filters out files already in SQLite metadata (deduplication)
    3. For each new file (up to batch_size per cycle):
       - Reads span metadata from Parquet
       - Indexes metadata into SQLite (parquet_files + trace_files + services)
    4. Handles errors gracefully (logs bad files, continues)
    5. Supports graceful shutdown (cancellation)

    Error Handling:
        - Missing storage path: Log and continue (ingestion might not have flushed yet)
        - Bad Parquet file: Log with full context (path, error), skip, continue
        - SQLite errors: Log and continue (retry on next cycle)
    """
    logger.info(
        "Starting parquet indexer",
        extra={
            "parquet_storage_path": settings.parquet_indexer.parquet_storage_path_resolved,
            "poll_interval": settings.parquet_indexer.poll_interval,
            "batch_size": settings.parquet_indexer.batch_size,
        },
    )

    executor = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="parquet-indexer",
    )

    try:
        while True:
            # Sleep first (poll interval)
            await asyncio.sleep(settings.parquet_indexer.poll_interval)

            try:
                await index_new_files(executor)
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
        executor.shutdown(wait=False, cancel_futures=True)
        logger.info("Parquet indexer stopped")


async def index_new_files(executor: ThreadPoolExecutor | None = None) -> int:
    """Scan for and index new Parquet files.

    The function is concurrency-safe; only one indexing pass can run at a time.

    Args:
        executor: Optional thread pool to use for blocking I/O. If not provided,
            a bounded single-worker executor is used for this call.

    Returns:
        Number of files successfully indexed in this cycle.
    """
    lock = _get_index_lock()
    async with lock:
        if executor is None:
            temp_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="parquet-indexer-on-demand",
            )
            try:
                return await _index_new_files(temp_executor)
            finally:
                temp_executor.shutdown(wait=False, cancel_futures=True)

        return await _index_new_files(executor)


async def _index_new_files(executor: ThreadPoolExecutor) -> int:
    """Scan for and index new Parquet files.

    This is the core indexing logic, extracted for testability.
    Uses SQLite as the sole metadata index.

    Returns:
        Number of files successfully indexed in this cycle.
    """
    # Run filesystem scan in thread pool (blocking I/O)
    loop = asyncio.get_running_loop()
    all_files = await loop.run_in_executor(
        executor, scan_parquet_files, settings.parquet_indexer.parquet_storage_path_resolved
    )

    if not all_files:
        logger.debug("No parquet files found in storage path")
        return 0

    # Get already-indexed paths from SQLite (deduplication checkpoint)
    indexed_paths = await loop.run_in_executor(executor, sqlite_repository.get_indexed_file_paths)

    # Get failed file paths to skip (don't retry known bad files)
    failed_paths = await loop.run_in_executor(executor, sqlite_repository.get_failed_file_paths)

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
                executor, read_parquet_metadata, file_info.path, file_info.size_bytes
            )

            # Index into SQLite metadata (blocking I/O)
            span_count = await loop.run_in_executor(
                executor, sqlite_indexer.index_parquet_file, file_data
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

            # Record failure to SQLite so we don't retry on next poll
            try:
                await loop.run_in_executor(
                    executor,
                    sqlite_repository.record_failed_file,
                    file_info.path,
                    error_type,
                    error_message,
                    file_info.size_bytes,
                )
            except Exception as record_err:
                logger.warning(
                    f"Failed to record failed file: {record_err}",
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
