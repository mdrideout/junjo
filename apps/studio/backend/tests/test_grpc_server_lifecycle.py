import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

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

    with (
        patch("app.main.os.getpid", return_value=1234),
        patch("app.main.os.kill") as kill,
    ):
        await _supervise_internal_grpc_server(server)

    server.wait_for_termination.assert_awaited_once_with()
    kill.assert_called_once_with(1234, signal.SIGTERM)


@pytest.mark.asyncio
async def test_grpc_supervision_failure_signals_process_shutdown() -> None:
    server = MagicMock()
    server.wait_for_termination = AsyncMock(side_effect=RuntimeError("gRPC failed"))

    with (
        patch("app.main.os.getpid", return_value=1234),
        patch("app.main.os.kill") as kill,
    ):
        await _supervise_internal_grpc_server(server)

    kill.assert_called_once_with(1234, signal.SIGTERM)


@pytest.mark.asyncio
async def test_normal_shutdown_cancels_supervision_before_stopping_grpc() -> None:
    wait_started = asyncio.Event()

    async def wait_for_termination() -> None:
        wait_started.set()
        await asyncio.Event().wait()

    server = MagicMock()
    server.wait_for_termination = wait_for_termination
    supervisor = asyncio.create_task(_supervise_internal_grpc_server(server))
    await wait_started.wait()

    with (
        patch("app.main.os.kill") as kill,
        patch("app.main.stop_grpc_server", new=AsyncMock()) as stop,
    ):
        await _shutdown_internal_grpc_server(supervisor)

    assert supervisor.cancelled()
    kill.assert_not_called()
    stop.assert_awaited_once_with()
