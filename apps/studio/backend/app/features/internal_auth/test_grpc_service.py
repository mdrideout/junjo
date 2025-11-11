"""
Unit tests for the internal authentication gRPC service.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.internal_auth.grpc_service import InternalAuthServicer
from app.proto_gen import auth_pb2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_api_key_valid():
    """Test ValidateApiKey returns is_valid=True for existing API key."""
    servicer = InternalAuthServicer()
    request = auth_pb2.ValidateApiKeyRequest(api_key="test_valid_key_12345")
    context = MagicMock()

    # Mock the repository to return a key (indicating it exists)
    with patch(
        "app.features.internal_auth.grpc_service.APIKeyRepository.get_by_key",
        new_callable=AsyncMock,
    ) as mock_get_by_key:
        mock_get_by_key.return_value = MagicMock(
            id="test_id", key="test_valid_key_12345", name="Test Key"
        )

        response = await servicer.ValidateApiKey(request, context)

        assert response.is_valid is True
        mock_get_by_key.assert_called_once_with("test_valid_key_12345")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_api_key_invalid():
    """Test ValidateApiKey returns is_valid=False for non-existent API key."""
    servicer = InternalAuthServicer()
    request = auth_pb2.ValidateApiKeyRequest(api_key="invalid_key_12345")
    context = MagicMock()

    # Mock the repository to raise an exception (key not found)
    with patch(
        "app.features.internal_auth.grpc_service.APIKeyRepository.get_by_key",
        new_callable=AsyncMock,
    ) as mock_get_by_key:
        mock_get_by_key.side_effect = Exception("No row was found")

        response = await servicer.ValidateApiKey(request, context)

        assert response.is_valid is False
        mock_get_by_key.assert_called_once_with("invalid_key_12345")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_api_key_database_error():
    """Test ValidateApiKey returns is_valid=False on database error (fail closed)."""
    servicer = InternalAuthServicer()
    request = auth_pb2.ValidateApiKeyRequest(api_key="test_key_12345")
    context = MagicMock()

    # Mock the repository to raise a database error
    with patch(
        "app.features.internal_auth.grpc_service.APIKeyRepository.get_by_key",
        new_callable=AsyncMock,
    ) as mock_get_by_key:
        mock_get_by_key.side_effect = Exception("Database connection failed")

        response = await servicer.ValidateApiKey(request, context)

        # Should fail closed (deny access on error)
        assert response.is_valid is False
        mock_get_by_key.assert_called_once_with("test_key_12345")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_api_key_empty():
    """Test ValidateApiKey handles empty API key."""
    servicer = InternalAuthServicer()
    request = auth_pb2.ValidateApiKeyRequest(api_key="")
    context = MagicMock()

    # Mock the repository to raise an exception for empty key
    with patch(
        "app.features.internal_auth.grpc_service.APIKeyRepository.get_by_key",
        new_callable=AsyncMock,
    ) as mock_get_by_key:
        mock_get_by_key.side_effect = Exception("No row was found")

        response = await servicer.ValidateApiKey(request, context)

        assert response.is_valid is False
        mock_get_by_key.assert_called_once_with("")
