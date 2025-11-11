"""
Internal authentication gRPC service for validating API keys.

This service provides the ValidateApiKey RPC endpoint used by the ingestion service
to validate API keys with caching support.
"""

import grpc
from loguru import logger

from app.db_sqlite.api_keys.repository import APIKeyRepository
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
