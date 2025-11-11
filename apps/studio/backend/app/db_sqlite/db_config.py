"""Database configuration for SQLAlchemy with SQLite.

High-concurrency async pattern validated from wt_api_v2:
- async_sessionmaker with expire_on_commit=False
- Each repository method creates its own session
- SQLite-specific PRAGMA settings for performance and safety

SQLite Idiosyncrasies:
- check_same_thread: False (required for async)
- PRAGMA foreign_keys=ON (enable FK constraints)
- PRAGMA journal_mode=WAL (Write-Ahead Logging for concurrency)
- PRAGMA synchronous=NORMAL (balance safety/performance)
- WAL checkpoint on shutdown

See: PYTHON_BACKEND_HIGH_CONCURRENCY_DB_PATTERN.md
"""

from loguru import logger
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import settings

# Create the async engine
engine = create_async_engine(
    settings.database.sqlite_url,
    echo=False,  # Set to True manually if you need to see SQL queries for debugging
    connect_args={"check_same_thread": False},  # Required for async SQLite
)


# Set PRAGMA settings for every new connection
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    """Configure SQLite PRAGMA settings on connection.

    Args:
        dbapi_connection: Raw SQLite connection
        connection_record: SQLAlchemy connection record

    PRAGMA settings:
        - foreign_keys=ON: Enable foreign key constraints (off by default in SQLite)
        - journal_mode=WAL: Write-Ahead Logging for better concurrency
        - synchronous=NORMAL: Balance between safety and performance
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


# Create the async session factory
# CRITICAL: expire_on_commit=False prevents lazy loading errors in async contexts
async_session = async_sessionmaker(
    engine,
    expire_on_commit=False,  # ⚠️ REQUIRED for asyncio safety
)

logger.info(f"Database engine created: {settings.database.sqlite_path}")

# Instrument SQLAlchemy for OpenTelemetry
SQLAlchemyInstrumentor().instrument(
    engine=engine.sync_engine,
    enable_commenter=True,
)

# Import all models to register them with Base.metadata
# This ensures Base.metadata.create_all() knows about all tables
from app.db_sqlite import models  # noqa: F401, E402


# Dependency to get DB session
async def get_db():
    """FastAPI dependency to get database session.

    Usage:
        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...

    Note:
        In Junjo, we primarily use the static repository pattern
        (repositories create their own sessions), but this dependency
        is available if needed.

    Yields:
        AsyncSession: Database session for the request
    """
    async with async_session() as session:
        yield session


async def checkpoint_wal():
    """Force a WAL checkpoint to ensure all transactions are written to the main database file.

    Should be called on application shutdown to ensure data persistence.
    WAL (Write-Ahead Logging) mode keeps changes in separate files until checkpoint.
    """
    async with engine.connect() as conn:
        logger.info("Checkpointing WAL")
        await conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE);"))
        logger.info("Checkpoint complete")
