"""
Internal gRPC service for ingestion ↔ backend communication.

This service provides:
- ValidateApiKey: API key validation for ingestion auth
"""

import secrets

import grpc
from loguru import logger

from app.config.settings import settings
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

        metadata = dict(context.invocation_metadata())
        supplied_token = metadata.get("x-junjo-internal-token", "")
        if not secrets.compare_digest(supplied_token, settings.internal_grpc_token):
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid internal workload token")
            raise RuntimeError("gRPC context.abort returned unexpectedly")

        logger.debug("Validating API key")

        try:
            # Try to get the API key from database
            result = await APIKeyRepository.get_by_key(api_key)

            # Check if key exists (get_by_key returns None if not found)
            if result is None:
                logger.debug("API key not found")
                return auth_pb2.ValidateApiKeyResponse(is_valid=False)

            # Key exists
            logger.debug("API key validation successful")
            return auth_pb2.ValidateApiKeyResponse(is_valid=True)

        except Exception as e:
            logger.error(
                "Database error during API key validation",
                extra={"error": str(e), "error_type": type(e).__name__},
            )

            await context.abort(grpc.StatusCode.UNAVAILABLE, "API key store unavailable")
            raise RuntimeError("gRPC context.abort returned unexpectedly")
