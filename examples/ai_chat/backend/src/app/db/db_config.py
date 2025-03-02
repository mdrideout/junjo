from pathlib import Path

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import SQABase

# Get the current file's path
current_file = Path(__file__)

# Get the project root (adjust the number of parent directories as needed)
project_root = current_file.parent.parent.parent.parent  # Adjust this level if necessary

# Create the database directory if it doesn't exist
database_dir = project_root / "sqlite-data"
database_dir.mkdir(parents=True, exist_ok=True)

# Construct the absolute path to the database file
db_path = database_dir / "sqlite.db"

logger.info("PATH: " + str(db_path))

DB_PATH = f"sqlite+aiosqlite:///{db_path}"

# Create the async engine
engine = create_async_engine(
    DB_PATH,
    echo=True,
    connect_args={"check_same_thread": False},
)

# Create the async session local class
async_session = async_sessionmaker(engine, expire_on_commit=False)


# Dependency to get DB session
async def get_db():
    async with async_session() as session:
        yield session


# Startup event
async def init_db():
    logger.info(f"Initializing database. Full path: {DB_PATH}")

    # Import table models here
    # Tables will not get created unless they are imported here
    from app.db.partner.model import ContactsTable  # noqa: F401

    async with engine.begin() as conn:
        # Create tables if they don't exist
        await conn.run_sync(SQABase.metadata.create_all)

        # Enable foreign keys for the initial connection
        await conn.execute(text("PRAGMA foreign_keys=ON"))

        # Potential performance optimization options
        # # Enable WAL mode for better concurrency
        # logger.info("Enabling WAL mode for SQLite")
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous = NORMAL"))

    logger.info("Database initialized successfully")
