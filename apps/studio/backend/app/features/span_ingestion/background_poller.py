"""Background poller for span ingestion from ingestion service.

This module implements an async infinite loop that:
1. Polls ingestion service every N seconds for new spans
2. Processes spans and indexes them in DuckDB
3. Updates poller state in SQLite for crash recovery

Port of: backend/main.go:78-160
"""

import asyncio

from loguru import logger

from app.config.settings import settings
from app.db_sqlite.db_config import async_session
from app.db_sqlite.poller_state.repository import PollerStateRepository
from app.features.span_ingestion.batch_preparation import unmarshal_spans_with_service_names
from app.features.span_ingestion.ingestion_client import IngestionClient
from app.features.span_ingestion.span_processor import process_span_batch


async def span_ingestion_poller() -> None:
    """Background task that polls ingestion service for new spans.

    This is an infinite async loop that:
    1. Loads last_key from SQLite on startup (or starts from beginning)
    2. Every SPAN_POLL_INTERVAL seconds:
       - Reads spans from ingestion service
       - Unmarshals OTLP protobufs and extracts per-span service_name
       - Processes spans in batch with correct service names (inserts to DuckDB)
       - Updates last_key in SQLite on success
    3. Handles errors gracefully (logs and continues)
    4. Supports graceful shutdown (cancellation)

    Error Handling:
        - Network errors: Log and continue polling
        - Unmarshal errors: Skip corrupted span, continue with batch
        - Processing errors: Log, don't update state, retry on next poll
        - State save errors: Log but continue (non-fatal)

    Reference: backend/main.go:78-160
    """
    logger.info("Starting span ingestion poller")

    # Initialize gRPC client
    client = IngestionClient()
    await client.connect()

    # Load last processed key from database
    async with async_session() as session:
        repo = PollerStateRepository(session)
        last_key = await repo.get_last_key()

        if last_key:
            logger.info(f"Resuming poller from key: {last_key.hex()}")
        else:
            logger.info("Starting poller from beginning (no saved state)")
            last_key = b""  # Empty bytes = start from beginning

    try:
        while True:
            # Sleep first (poll interval)
            await asyncio.sleep(settings.span_ingestion.SPAN_POLL_INTERVAL)

            try:
                logger.debug("Polling for new spans")

                # 1. Read spans from ingestion service
                spans_with_resources, remaining_count = await client.read_spans(
                    last_key, batch_size=settings.span_ingestion.SPAN_BATCH_SIZE
                )

                if not spans_with_resources:
                    logger.debug(
                        "No new spans found",
                        extra={"remaining_unretrieved": remaining_count},
                    )
                    continue

                logger.info(
                    f"Received {len(spans_with_resources)} spans from ingestion service",
                    extra={"remaining_unretrieved": remaining_count},
                )

                # 2. Update last_key for next poll (even if spans are empty/corrupted)
                last_key = spans_with_resources[-1].key_ulid

                # 3. Filter out dummy cursor-advancing spans (empty span_bytes)
                real_spans = [s for s in spans_with_resources if s.span_bytes]

                if not real_spans:
                    # All spans were corrupted/empty - cursor was advanced automatically
                    logger.info(
                        "Cursor advanced past corrupted spans, no processable data in batch",
                        extra={
                            "batch_size": len(spans_with_resources),
                            "remaining_unretrieved": remaining_count,
                            "last_key": last_key.hex(),
                        },
                    )
                    # Save the advanced cursor position
                    async with async_session() as session:
                        repo = PollerStateRepository(session)
                        await repo.upsert_last_key(last_key)
                        await session.commit()
                    continue

                # 4. Unmarshal spans and extract per-span service names
                spans_with_service_names = unmarshal_spans_with_service_names(real_spans)

                if not spans_with_service_names:
                    logger.warning(
                        "All spans failed to unmarshal, skipping batch",
                        extra={"received": len(real_spans)},
                    )
                    # Still save cursor to avoid infinite retry
                    async with async_session() as session:
                        repo = PollerStateRepository(session)
                        await repo.upsert_last_key(last_key)
                        await session.commit()
                    continue

                # 4. Process spans in batch (single transaction, correct service names)
                try:
                    process_span_batch(spans_with_service_names)

                    # 5. Save poller state on success
                    async with async_session() as session:
                        repo = PollerStateRepository(session)
                        await repo.upsert_last_key(last_key)
                        await session.commit()

                    logger.info(
                        f"Successfully processed batch of {len(spans_with_service_names)} spans, state saved",
                        extra={
                            "processed": len(spans_with_service_names),
                            "last_key": last_key.hex(),
                        },
                    )

                except Exception as e:
                    logger.error(
                        "Error processing spans",
                        extra={
                            "batch_size": len(spans_with_service_names),
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                    )
                    # Don't update state - retry batch on next poll

            except Exception as e:
                logger.error(
                    "Error in poll cycle",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "last_key": last_key.hex() if last_key else "None",
                    },
                )
                continue  # Continue polling on error

    finally:
        await client.close()
        logger.info("Span ingestion poller stopped")
