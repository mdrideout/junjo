from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.grpc_server as grpc_server


def test_create_grpc_server_fails_when_port_cannot_bind() -> None:
    server = MagicMock()
    server.add_insecure_port.return_value = 0
    with patch("app.grpc_server.grpc.aio.server", return_value=server):
        with pytest.raises(RuntimeError, match="Unable to bind internal gRPC port"):
            grpc_server.create_grpc_server()


@pytest.mark.asyncio
async def test_start_grpc_server_waits_for_positive_start() -> None:
    server = MagicMock()
    server.start = AsyncMock()
    grpc_server._grpc_server = None

    with patch("app.grpc_server.create_grpc_server", return_value=server):
        started = await grpc_server.start_grpc_server()

    assert started is server
    server.start.assert_awaited_once_with()
    grpc_server._grpc_server = None
