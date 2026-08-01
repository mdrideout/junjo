import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

import app.grpc_server as grpc_server
from app.main import _shutdown_internal_grpc_server, _supervise_internal_grpc_server


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


@pytest.mark.asyncio
async def test_unexpected_grpc_termination_signals_process_shutdown() -> None:
    server = MagicMock()
    server.wait_for_termination = AsyncMock()
    shutdown_requested = asyncio.Event()

    with (
        patch("app.main.os.getpid", return_value=1234),
        patch("app.main.os.kill") as kill,
    ):
        await _supervise_internal_grpc_server(server, shutdown_requested)

    server.wait_for_termination.assert_awaited_once_with()
    kill.assert_called_once_with(1234, signal.SIGTERM)


@pytest.mark.asyncio
async def test_grpc_supervision_failure_signals_process_shutdown() -> None:
    server = MagicMock()
    server.wait_for_termination = AsyncMock(side_effect=RuntimeError("gRPC failed"))
    shutdown_requested = asyncio.Event()

    with (
        patch("app.main.os.getpid", return_value=1234),
        patch("app.main.os.kill") as kill,
    ):
        await _supervise_internal_grpc_server(server, shutdown_requested)

    kill.assert_called_once_with(1234, signal.SIGTERM)


@pytest.mark.asyncio
async def test_normal_shutdown_stops_real_grpc_server_before_awaiting_supervision() -> None:
    server = grpc.aio.server()
    bound_port = server.add_insecure_port("127.0.0.1:0")
    assert bound_port != 0
    await server.start()

    shutdown_requested = asyncio.Event()
    grpc_server._grpc_server = server
    supervisor = asyncio.create_task(_supervise_internal_grpc_server(server, shutdown_requested))
    await asyncio.sleep(0)

    try:
        with patch("app.main.os.kill") as kill:
            await _shutdown_internal_grpc_server(supervisor, shutdown_requested)

        assert supervisor.done()
        assert not supervisor.cancelled()
        assert grpc_server._grpc_server is None
        kill.assert_not_called()
    finally:
        if grpc_server._grpc_server is not None:
            await grpc_server.stop_grpc_server()
