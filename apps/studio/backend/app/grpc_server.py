"""
gRPC server for internal authentication services.

This module creates and manages a gRPC server that runs concurrently with FastAPI,
providing the InternalAuthService for the ingestion service to validate API keys.
"""

import grpc
from loguru import logger

from app.config.settings import settings
from app.features.internal_auth.grpc_service import InternalAuthServicer
from app.proto_gen import auth_pb2_grpc

# Global reference to the gRPC server for graceful shutdown
_grpc_server: grpc.aio.Server | None = None


def create_grpc_server() -> grpc.aio.Server:
    """
    Create and configure the gRPC server with all services.

    Returns:
        Configured gRPC async server instance
    """
    server = grpc.aio.server()

    # Register the InternalAuthService
    auth_pb2_grpc.add_InternalAuthServiceServicer_to_server(InternalAuthServicer(), server)

    # Bind to port (IPv4 - works better on macOS for dev)
    grpc_port = settings.GRPC_PORT
    server.add_insecure_port(f"0.0.0.0:{grpc_port}")

    logger.info(f"gRPC server configured on port {grpc_port}")
    return server


async def start_grpc_server_background() -> None:
    """
    Start the gRPC server as a background asyncio task.

    This function is designed to be called from FastAPI's startup event.
    It starts the gRPC server and keeps it running in the background.
    """
    global _grpc_server

    try:
        _grpc_server = create_grpc_server()
        await _grpc_server.start()
        logger.info(f"✓ gRPC server started on port {settings.GRPC_PORT}")

        # Keep the server running
        await _grpc_server.wait_for_termination()

    except Exception as e:
        logger.error(f"gRPC server failed to start: {e}")
        raise


async def stop_grpc_server() -> None:
    """
    Gracefully stop the gRPC server.

    This function is designed to be called from FastAPI's shutdown event.
    """
    global _grpc_server

    if _grpc_server is not None:
        logger.info("Stopping gRPC server...")
        await _grpc_server.stop(grace=5.0)  # 5 second grace period
        _grpc_server = None
        logger.info("✓ gRPC server stopped")
