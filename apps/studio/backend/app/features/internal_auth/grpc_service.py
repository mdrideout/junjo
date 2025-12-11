"""
Internal gRPC service for ingestion ↔ backend communication.

This service provides:
- ValidateApiKey: API key validation for ingestion auth
- NotifyNewParquetFile: Immediate indexing notification after cold flush
"""

import grpc
from loguru import logger

from app.db_sqlite.api_keys.repository import APIKeyRepository
from app.features.parquet_indexer.background_indexer import index_new_files
from app.proto_gen import auth_pb2, auth_pb2_grpc


class InternalAuthServicer(auth_pb2_grpc.InternalAuthServiceServicer):
    """
    gRPC servicer implementation for internal API key authentication.

    This service is called by the ingestion service to validate API keys.
    It queries the database to check if a key exists and is valid.
    """

    async def ValidateApiKey(  # noqa: N802 - gRPC method names follow protobuf convention
        self,
        request: auth_pb2.ValidateApiKeyRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.ValidateApiKeyResponse:
        """
        Validate an API key by checking if it exists in the database.

        Args:
            request: ValidateApiKeyRequest containing the API key to validate
            context: gRPC servicer context

        Returns:
            ValidateApiKeyResponse with is_valid=True if key exists, False otherwise
        """
        api_key = request.api_key

        # Log validation attempt (without logging the full key for security)
        key_prefix = api_key[:12] if len(api_key) >= 12 else "***"
        logger.info(f"Validating API key: {key_prefix}...")

        try:
            # Try to get the API key from database
            result = await APIKeyRepository.get_by_key(api_key)

            # Check if key exists (get_by_key returns None if not found)
            if result is None:
                logger.info(f"API key not found: {key_prefix}...")
                return auth_pb2.ValidateApiKeyResponse(is_valid=False)

            # Key exists
            logger.info(f"API key validation successful: {key_prefix}...")
            return auth_pb2.ValidateApiKeyResponse(is_valid=True)

        except Exception as e:
            # Database error - fail closed (deny access)
            logger.error(
                "Database error during API key validation",
                extra={"error": str(e), "error_type": type(e).__name__},
            )

            # Return False instead of raising error (fail closed)
            # The ingestion service will treat this as invalid
            return auth_pb2.ValidateApiKeyResponse(is_valid=False)

    async def NotifyNewParquetFile(  # noqa: N802 - gRPC method names follow protobuf convention
        self,
        request: auth_pb2.NotifyNewParquetFileRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.NotifyNewParquetFileResponse:
        """
        Trigger indexing after a new parquet file is flushed.

        Called by ingestion after a cold flush completes, avoiding the polling delay.
        This triggers the normal indexing logic which will find and index the new file.

        Args:
            request: NotifyNewParquetFileRequest containing the file path (for logging)
            context: gRPC servicer context

        Returns:
            NotifyNewParquetFileResponse with indexing result
        """
        file_path = request.file_path
        logger.info(f"Received notification for new parquet file: {file_path}")

        try:
            # Trigger the normal indexing function - it handles:
            # - File scanning and deduplication
            # - Reading parquet metadata
            # - Indexing to DuckDB
            # - Error recording for bad files
            indexed_count = await index_new_files()

            logger.info(f"Indexing triggered, indexed {indexed_count} files")
            return auth_pb2.NotifyNewParquetFileResponse(indexed=True, span_count=indexed_count)

        except Exception as e:
            logger.error(
                f"Failed to trigger indexing after notification: {file_path}",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return auth_pb2.NotifyNewParquetFileResponse(indexed=False, span_count=0)
