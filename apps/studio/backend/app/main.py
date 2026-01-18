"""
Main FastAPI application entry point.

Sets up the FastAPI app with:
- CORS middleware
- Loguru logging
- Health check endpoints
- Feature routers (will be added in later phases)
- gRPC server for internal authentication (runs concurrently)

Pattern from wt_api_v2 (validated for production use).
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from securecookies import SecureCookiesMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.common.responses import HealthResponse
from app.config.deployment_validation import log_deployment_configuration
from app.config.logger import setup_logging
from app.config.settings import settings
from app.features.admin.router import router as admin_router
from app.features.api_keys.router import router as api_keys_router
from app.features.auth.router import router as auth_router
from app.features.config.router import router as config_router
from app.features.llm_playground.router import router as llm_playground_router
from app.features.otel_spans.router import router as otel_spans_router
from app.grpc_server import start_grpc_server_background, stop_grpc_server

# Set up logging before anything else
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown events for the FastAPI application.
    Logs startup configuration, starts gRPC server, and performs cleanup on shutdown.

    Args:
        app: FastAPI application instance.

    Yields:
        Control to the application runtime.
    """
    # Startup
    logger.info("=" * 60)
    logger.info("Starting Junjo AI Studio")
    logger.info("Python 3.13+ with Pydantic v2")
    logger.info(f"FastAPI Server: http://0.0.0.0:{settings.port}")
    logger.info(f"gRPC Server: [::]:{settings.GRPC_PORT}")
    logger.info(f"CORS origins: {settings.cors_origins}")
    logger.info("=" * 60)

    # Configure LiteLLM environment variables
    if settings.llm.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.llm.openai_api_key
        logger.info("OpenAI API key configured")
    if settings.llm.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = settings.llm.anthropic_api_key
        logger.info("Anthropic API key configured")
    if settings.llm.gemini_api_key:
        os.environ["GEMINI_API_KEY"] = settings.llm.gemini_api_key
        logger.info("Gemini API key configured")

    # Initialize SQLite metadata index
    from app.db_sqlite.metadata import init_metadata_db
    from app.db_sqlite.metadata.maintenance import sync_with_filesystem

    init_metadata_db(settings.database.metadata_db_path_resolved)
    logger.info("SQLite metadata index initialized")

    # Sync metadata index with filesystem (remove orphaned entries)
    sync_result = sync_with_filesystem(settings.parquet_indexer.parquet_storage_path_resolved)
    if sync_result["removed"] > 0 or sync_result["missing"]:
        logger.info(
            "Metadata index synced with filesystem",
            extra={
                "removed_orphans": sync_result["removed"],
                "missing_files": len(sync_result["missing"]),
            },
        )

    # Log deployment configuration
    log_deployment_configuration()

    # V4 Architecture: Start Parquet indexer as background task
    # Polls filesystem for Parquet files written by Go ingestion
    from app.features.parquet_indexer.background_indexer import parquet_indexer

    indexer_task = asyncio.create_task(parquet_indexer())
    logger.info("Parquet indexer task created")

    # Start gRPC server as background task
    grpc_task = asyncio.create_task(start_grpc_server_background())
    logger.info("gRPC server task created")

    yield

    # Shutdown
    logger.info("Shutting down application")

    # Stop Parquet indexer (V4)
    if not indexer_task.done():
        indexer_task.cancel()
        try:
            await indexer_task
        except asyncio.CancelledError:
            logger.info("Parquet indexer cancelled")

    # Stop gRPC server
    await stop_grpc_server()

    # Cancel gRPC task if still running
    if not grpc_task.done():
        grpc_task.cancel()
        try:
            await grpc_task
        except asyncio.CancelledError:
            logger.info("gRPC task cancelled")

    # Database cleanup
    from app.db_sqlite.db_config import checkpoint_wal, engine
    from app.db_sqlite.metadata import checkpoint_wal as metadata_checkpoint_wal

    await checkpoint_wal()  # Checkpoint SQLite WAL (user data)
    logger.info("SQLite WAL checkpointed")
    metadata_checkpoint_wal()  # Checkpoint metadata WAL (synchronous)
    logger.info("Metadata WAL checkpointed")
    await engine.dispose()  # Close database connections
    logger.info("Database connections closed")


# Create FastAPI app
app = FastAPI(
    title="Junjo AI Studio",
    description="LLM Observability Platform - Python Backend",
    version="0.1.0",
    lifespan=lifespan,
    # Disable Swagger UI and ReDoc (not needed for production deployments)
    docs_url=None,
    redoc_url=None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === SESSION/AUTH MIDDLEWARE (ORDER IS CRITICAL!) ===

# 1. Add ENCRYPTION middleware FIRST (outer layer)
#    This encrypts/decrypts all cookies before they reach SessionMiddleware
app.add_middleware(
    SecureCookiesMiddleware,
    secrets=[settings.secure_cookie_key],  # 32-byte encryption key
)

# 2. Add SESSION middleware SECOND (inner layer)
#    This signs/validates session data
#    https_only should be True in production, False in development/test
is_production = settings.junjo_env == "production"
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,  # Signing key
    max_age=86400 * 30,  # 30 days (matches Go implementation)
    https_only=is_production,  # HTTPS required in production only
    same_site="strict",  # CSRF protection
)

# === REQUEST/RESPONSE FLOW ===
# Incoming:  Browser → SecureCookiesMiddleware (decrypt) → SessionMiddleware (verify signature) → request.session populated
# Outgoing:  request.session modified → SessionMiddleware (sign) → SecureCookiesMiddleware (encrypt) → Browser

# === ROUTERS ===
app.include_router(admin_router, prefix="/api")
app.include_router(auth_router, tags=["auth"])
app.include_router(api_keys_router)
app.include_router(config_router, prefix="/api")
app.include_router(llm_playground_router, prefix="/llm", tags=["llm"])
app.include_router(otel_spans_router, prefix="/api/v1/observability", tags=["observability"])


# Health check endpoints
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    """Detailed health check endpoint.

    Returns:
        HealthResponse with status, version, and application name.
    """
    logger.debug("Health endpoint called")
    return HealthResponse(
        status="ok",
        version="0.1.0",
        app_name="Junjo AI Studio",
    )


# Root endpoint
@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """Root endpoint with API information.

    Returns:
        Dictionary containing app name, version, and health check link.
    """
    return {
        "app": "Junjo AI Studio",
        "version": "0.1.0",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    # Auto-reload in development only
    reload = settings.junjo_env == "development"

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # Listen on all interfaces (required for Docker)
        port=settings.port,
        reload=reload,
        log_config=None,  # Disable uvicorn logging (we use loguru)
    )
