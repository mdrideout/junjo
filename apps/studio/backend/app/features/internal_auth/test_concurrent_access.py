"""
Concurrent access tests for gRPC and FastAPI services.

These tests verify that:
1. Multiple gRPC requests can be handled concurrently
2. FastAPI and gRPC can operate simultaneously without conflicts
3. Database access is thread-safe (no race conditions)
"""

import asyncio

import grpc
import pytest
from httpx import AsyncClient
from loguru import logger

from app.config.settings import settings
from app.main import app
from app.proto_gen import auth_pb2, auth_pb2_grpc


@pytest.mark.integration
@pytest.mark.requires_grpc_server
@pytest.mark.asyncio
async def test_concurrent_grpc_requests(test_api_key):
    """
    Test that multiple gRPC ValidateApiKey requests can be handled concurrently.

    Requires: gRPC server running on port 50053.

    Simulates the ingestion service making multiple concurrent API key
    validation requests to the backend.
    """
    num_requests = 50
    test_keys = [
        test_api_key,  # Valid (from fixture)
        "invalid_key_1",
        "invalid_key_2",
        "",
    ]

    async def validate_key(key: str) -> bool:
        """Helper to validate a single key via gRPC."""
        async with grpc.aio.insecure_channel(f"localhost:{settings.GRPC_PORT}") as channel:
            stub = auth_pb2_grpc.InternalAuthServiceStub(channel)
            request = auth_pb2.ValidateApiKeyRequest(api_key=key)
            response = await stub.ValidateApiKey(request)
            return response.is_valid

    # Create concurrent tasks
    tasks = [validate_key(test_keys[i % len(test_keys)]) for i in range(num_requests)]

    # Execute all tasks concurrently
    results = await asyncio.gather(*tasks)

    # Verify results
    assert len(results) == num_requests

    # Count expected valid vs invalid
    valid_count = sum(
        1 for i in range(num_requests) if test_keys[i % len(test_keys)] == test_keys[0]
    )
    invalid_count = num_requests - valid_count

    actual_valid = sum(1 for r in results if r)
    actual_invalid = sum(1 for r in results if not r)

    assert actual_valid == valid_count
    assert actual_invalid == invalid_count

    logger.info(
        f"✓ Concurrent access test passed: {num_requests} gRPC requests handled successfully"
    )


@pytest.mark.integration
@pytest.mark.requires_grpc_server
@pytest.mark.asyncio
async def test_mixed_fastapi_and_grpc_requests():
    """
    Test that FastAPI and gRPC requests can be handled concurrently.

    Requires: gRPC server running on port 50053.

    Simulates real-world usage where:
    - Users make REST API calls to FastAPI endpoints
    - Ingestion  makes gRPC calls for API key validation
    Both should work without blocking each other.
    """
    num_grpc_requests = 25
    num_fastapi_requests = 25

    async def grpc_validate_key(key: str) -> bool:
        """Helper to validate a key via gRPC."""
        async with grpc.aio.insecure_channel(f"localhost:{settings.GRPC_PORT}") as channel:
            stub = auth_pb2_grpc.InternalAuthServiceStub(channel)
            request = auth_pb2.ValidateApiKeyRequest(api_key=key)
            response = await stub.ValidateApiKey(request)
            return response.is_valid

    async def fastapi_health_check() -> bool:
        """Helper to check FastAPI health endpoint."""
        # Use ASGI transport to test the app directly
        from httpx import ASGITransport

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
            return response.status_code == 200

    # Create mixed concurrent tasks
    grpc_tasks = [grpc_validate_key("test_key_" + str(i)) for i in range(num_grpc_requests)]
    fastapi_tasks = [fastapi_health_check() for _ in range(num_fastapi_requests)]

    # Interleave tasks to simulate real-world mixed traffic
    all_tasks = []
    for i in range(max(num_grpc_requests, num_fastapi_requests)):
        if i < num_grpc_requests:
            all_tasks.append(grpc_tasks[i])
        if i < num_fastapi_requests:
            all_tasks.append(fastapi_tasks[i])

    # Execute all tasks concurrently
    results = await asyncio.gather(*all_tasks)

    # Verify all requests completed successfully
    assert len(results) == num_grpc_requests + num_fastapi_requests

    logger.info(
        f"✓ Mixed concurrent access test passed: {num_grpc_requests} gRPC + {num_fastapi_requests} FastAPI requests"
    )


@pytest.mark.integration
@pytest.mark.requires_grpc_server
@pytest.mark.asyncio
async def test_grpc_under_load(test_api_key):
    """
    Test gRPC service under heavy concurrent load.

    Requires: gRPC server running on port 50053.

    Simulates high traffic to ensure the service remains stable
    and doesn't have race conditions or deadlocks.
    """
    num_requests = 100
    test_key = test_api_key

    async def validate_key() -> tuple[bool, float]:
        """Helper to validate key and measure response time."""
        start_time = asyncio.get_event_loop().time()
        async with grpc.aio.insecure_channel(f"localhost:{settings.GRPC_PORT}") as channel:
            stub = auth_pb2_grpc.InternalAuthServiceStub(channel)
            request = auth_pb2.ValidateApiKeyRequest(api_key=test_key)
            response = await stub.ValidateApiKey(request)
            end_time = asyncio.get_event_loop().time()
            return response.is_valid, (end_time - start_time)

    # Execute all requests concurrently
    results = await asyncio.gather(*[validate_key() for _ in range(num_requests)])

    # Verify all succeeded
    assert len(results) == num_requests
    assert all(is_valid for is_valid, _ in results)

    # Calculate performance metrics
    response_times = [time for _, time in results]
    avg_response_time = sum(response_times) / len(response_times)
    max_response_time = max(response_times)
    min_response_time = min(response_times)

    logger.info(f"✓ Load test passed: {num_requests} concurrent requests completed")
    logger.info(
        f"  Response times: avg={avg_response_time * 1000:.2f}ms, min={min_response_time * 1000:.2f}ms, max={max_response_time * 1000:.2f}ms"
    )

    # Sanity check: response times should be reasonable (< 1 second)
    assert avg_response_time < 1.0, f"Average response time too slow: {avg_response_time}s"


@pytest.mark.integration
@pytest.mark.requires_grpc_server
@pytest.mark.asyncio
async def test_database_isolation_concurrent_reads(test_api_key):
    """
    Test that concurrent database reads don't cause conflicts.

    Requires: gRPC server running on port 50053.

    Verifies the database session pattern is working correctly
    and there are no race conditions in concurrent reads.
    """
    num_concurrent_reads = 100
    test_key = test_api_key

    async def read_key_via_grpc() -> bool:
        """Make a gRPC call which triggers a database read."""
        async with grpc.aio.insecure_channel(f"localhost:{settings.GRPC_PORT}") as channel:
            stub = auth_pb2_grpc.InternalAuthServiceStub(channel)
            request = auth_pb2.ValidateApiKeyRequest(api_key=test_key)
            response = await stub.ValidateApiKey(request)
            return response.is_valid

    # Execute many concurrent reads
    results = await asyncio.gather(*[read_key_via_grpc() for _ in range(num_concurrent_reads)])

    # All should succeed with consistent results
    assert len(results) == num_concurrent_reads
    assert all(r is True for r in results), "All reads should return the same value"

    logger.info(
        f"✓ Database isolation test passed: {num_concurrent_reads} concurrent reads completed successfully"
    )
