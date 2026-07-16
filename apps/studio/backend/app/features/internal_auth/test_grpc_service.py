"""
Unit tests for the internal authentication gRPC service.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

from app.config.settings import settings
from app.features.internal_auth.grpc_service import InternalAuthServicer
from app.proto_gen import auth_pb2


def authenticated_context() -> MagicMock:
    context = MagicMock()
    context.invocation_metadata.return_value = (
        ("x-junjo-internal-token", settings.internal_grpc_token),
    )
    context.abort = AsyncMock()
    return context


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_api_key_valid():
    """Test ValidateApiKey returns is_valid=True for existing API key."""
    servicer = InternalAuthServicer()
    request = auth_pb2.ValidateApiKeyRequest(api_key="fixture-valid-key")
    context = authenticated_context()

    # Mock the repository to return a key (indicating it exists)
    with patch(
        "app.features.internal_auth.grpc_service.APIKeyRepository.get_by_key",
        new_callable=AsyncMock,
    ) as mock_get_by_key:
        mock_get_by_key.return_value = MagicMock(
            id="test_id", key="fixture-valid-key", name="Test Key"
        )

        response = await servicer.ValidateApiKey(request, context)

        assert response.is_valid is True
        mock_get_by_key.assert_called_once_with("fixture-valid-key")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_api_key_invalid():
    """Test ValidateApiKey returns is_valid=False for non-existent API key."""
    servicer = InternalAuthServicer()
    request = auth_pb2.ValidateApiKeyRequest(api_key="fixture-missing-key")
    context = authenticated_context()

    # A missing row is an authoritative invalid-key result.
    with patch(
        "app.features.internal_auth.grpc_service.APIKeyRepository.get_by_key",
        new_callable=AsyncMock,
    ) as mock_get_by_key:
        mock_get_by_key.return_value = None

        response = await servicer.ValidateApiKey(request, context)

        assert response.is_valid is False
        mock_get_by_key.assert_called_once_with("fixture-missing-key")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_api_key_database_error():
    """Test database failure is retryable UNAVAILABLE, not an invalid key."""
    servicer = InternalAuthServicer()
    request = auth_pb2.ValidateApiKeyRequest(api_key="test_key_12345")
    context = authenticated_context()

    # Mock the repository to raise a database error
    with patch(
        "app.features.internal_auth.grpc_service.APIKeyRepository.get_by_key",
        new_callable=AsyncMock,
    ) as mock_get_by_key:
        mock_get_by_key.side_effect = Exception("Database connection failed")

        with pytest.raises(RuntimeError, match="context.abort returned"):
            await servicer.ValidateApiKey(request, context)

        context.abort.assert_awaited_once_with(
            grpc.StatusCode.UNAVAILABLE,
            "API key store unavailable",
        )
        mock_get_by_key.assert_called_once_with("test_key_12345")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_api_key_empty():
    """Test ValidateApiKey handles empty API key."""
    servicer = InternalAuthServicer()
    request = auth_pb2.ValidateApiKeyRequest(api_key="")
    context = authenticated_context()

    # Empty input is an authoritative miss.
    with patch(
        "app.features.internal_auth.grpc_service.APIKeyRepository.get_by_key",
        new_callable=AsyncMock,
    ) as mock_get_by_key:
        mock_get_by_key.return_value = None

        response = await servicer.ValidateApiKey(request, context)

        assert response.is_valid is False
        mock_get_by_key.assert_called_once_with("")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_api_key_rejects_missing_workload_token():
    servicer = InternalAuthServicer()
    context = MagicMock()
    context.invocation_metadata.return_value = ()
    context.abort = AsyncMock()

    with pytest.raises(RuntimeError, match="context.abort returned"):
        await servicer.ValidateApiKey(
            auth_pb2.ValidateApiKeyRequest(api_key="fixture-valid-key"),
            context,
        )

    context.abort.assert_awaited_once_with(
        grpc.StatusCode.UNAUTHENTICATED,
        "Invalid internal workload token",
    )
