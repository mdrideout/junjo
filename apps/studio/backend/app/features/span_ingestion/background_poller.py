"""Background poller for span ingestion from ingestion service.

This module implements an async infinite loop that:
1. Polls ingestion service every N seconds for new spans
2. Processes spans and indexes them in DuckDB
3. Updates poller state in SQLite for crash recovery

Port of: backend/main.go:78-160
"""

import asyncio

from loguru import logger
from opentelemetry.proto.resource.v1 import resource_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

from app.config.settings import settings
from app.db_sqlite.db_config import async_session
from app.db_sqlite.poller_state.repository import PollerStateRepository
from app.features.span_ingestion.ingestion_client import IngestionClient
from app.features.span_ingestion.span_processor import process_span_batch


async def span_ingestion_poller() -> None:
    """Background task that polls ingestion service for new spans.

    This is an infinite async loop that:
    1. Loads last_key from SQLite on startup (or starts from beginning)
    2. Every SPAN_POLL_INTERVAL seconds:
       - Reads spans from ingestion service
       - Unmarshals OTLP protobufs
       - Extracts service_name from resource
       - Processes spans in batch (inserts to DuckDB)
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
                spans_with_resources = await client.read_spans(
                    last_key, batch_size=settings.span_ingestion.SPAN_BATCH_SIZE
                )

                if not spans_with_resources:
                    logger.debug("No new spans found")
                    continue

                logger.info(f"Received {len(spans_with_resources)} spans from ingestion service")

                # 2. Update last_key for next poll
                last_key = spans_with_resources[-1].key_ulid

                # 3. Unmarshal span protobufs
                processed_spans = []
                for span_with_resource in spans_with_resources:
                    try:
                        span = trace_pb2.Span()
                        span.ParseFromString(span_with_resource.span_bytes)
                        processed_spans.append(span)
                    except Exception as e:
                        logger.warning(
                            "Error unmarshaling span",
                            extra={
                                "key_ulid": span_with_resource.key_ulid.hex(),
                                "error": str(e),
                                "error_type": type(e).__name__,
                            },
                        )
                        continue  # Skip corrupted span

                if not processed_spans:
                    logger.warning(
                        "All spans failed to unmarshal, skipping batch",
                        extra={"received": len(spans_with_resources)},
                    )
                    continue

                # 4. Extract service_name from first span's resource
                service_name = "NO_SERVICE_NAME"
                if spans_with_resources:
                    try:
                        resource = resource_pb2.Resource()
                        resource.ParseFromString(spans_with_resources[0].resource_bytes)

                        for attr in resource.attributes:
                            if attr.key == "service.name" and attr.value.HasField("string_value"):
                                service_name = attr.value.string_value
                                break

                        if service_name == "NO_SERVICE_NAME":
                            logger.warning(
                                "No service.name attribute found in resource, using default"
                            )
                    except Exception as e:
                        logger.warning(
                            "Error extracting service name, using default",
                            extra={
                                "error": str(e),
                                "error_type": type(e).__name__,
                            },
                        )

                # 5. Process spans in batch (with transaction)
                try:
                    process_span_batch(service_name, processed_spans)

                    # 6. Save poller state on success
                    async with async_session() as session:
                        repo = PollerStateRepository(session)
                        await repo.upsert_last_key(last_key)
                        await session.commit()

                    logger.info(
                        f"Successfully processed batch of {len(processed_spans)} spans, state saved",
                        extra={
                            "processed": len(processed_spans),
                            "last_key": last_key.hex(),
                            "service_name": service_name,
                        },
                    )

                except Exception as e:
                    logger.error(
                        "Error processing spans",
                        extra={
                            "batch_size": len(processed_spans),
                            "service_name": service_name,
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
