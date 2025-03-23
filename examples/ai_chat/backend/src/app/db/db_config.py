from pathlib import Path
from urllib.parse import urlparse

from loguru import logger
from opentelemetry import trace
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
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
    from app.db.models.chat.model import ChatsTable  # noqa: F401
    from app.db.models.chat_members.model import ChatMembersTable  # noqa: F401
    from app.db.models.contact.model import ContactsTable  # noqa: F401
    from app.db.models.message.model import MessagesTable  # noqa: F401

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


# --- OpenTelemetry Instrumentation ---
def add_details(span, conn, cursor, statement, parameters, context, exception_):
    """Adds more details to the SQLAlchemy span."""
    # **Crucial: Set db.system**
    db_system = conn.dialect.name
    span.set_attribute("db.system", db_system)

    # Database Name
    parsed_url = urlparse(str(conn.engine.url))
    db_name = parsed_url.path.lstrip("/")  # Remove leading slash
    if not db_name:
        db_name = "Unknown SQLite"
    span.set_attribute("db.name", db_name)

    # db.user
    span.set_attribute("db.user", conn.engine.url.username or "default")

    # net.peer.name
    span.set_attribute("net.peer.name", parsed_url.hostname)

    # net.peer.port
    span.set_attribute("net.peer.port", parsed_url.port or (3306 if db_system == "mysql" else 5432 if db_system == "postgresql" else 0))

    # SQL Statement Type (db.operation)
    statement_lower = statement.lower()
    if statement_lower.startswith("select"):
        span.set_attribute("db.operation", "SELECT")
    elif statement_lower.startswith("insert"):
        span.set_attribute("db.operation", "INSERT")
    elif statement_lower.startswith("update"):
        span.set_attribute("db.operation", "UPDATE")
    elif statement_lower.startswith("delete"):
        span.set_attribute("db.operation", "DELETE")
    elif statement_lower.startswith("create"):
        span.set_attribute("db.operation", "CREATE")
    elif statement_lower.startswith("alter"):
        span.set_attribute("db.operation", "ALTER")
    elif statement_lower.startswith("drop"):
        span.set_attribute("db.operation", "DROP")
    else:
        span.set_attribute("db.operation", "OTHER")

    # Table Name (basic extraction)
    if "from" in statement_lower:
        parts = statement_lower.split("from")
        if len(parts) > 1:
            table_part = parts[1].split()[0]  # Get the first word after "from"
            span.set_attribute("db.sql.table", table_part)
    elif "into" in statement_lower:
        parts = statement_lower.split("into")
        if len(parts) > 1:
            table_part = parts[1].split()[0]  # Get the first word after "into"
            span.set_attribute("db.sql.table", table_part)
    elif "table" in statement_lower:
        parts = statement_lower.split("table")
        if len(parts) > 1:
            table_part = parts[1].split()[0]  # Get the first word after "table"
            span.set_attribute("db.sql.table", table_part)

    # Row Count (if available)
    if cursor and hasattr(cursor, "rowcount"):
        span.set_attribute("db.rowcount", cursor.rowcount)

    # Parameters
    if parameters:
        span.set_attribute("db.params", str(parameters))

    # db.statement
    span.set_attribute("db.statement", statement)

    # Exception Handling
    if exception_:
        span.set_status(trace.Status(trace.StatusCode.ERROR))
        span.record_exception(exception_)

    # Get isolation level
    try:
        isolation_level = conn.get_isolation_level()
        span.set_attribute("db.connection.isolation_level", isolation_level)
    except AttributeError:
        span.set_attribute("db.connection.isolation_level", "N/A")

    # db.connection.string
    span.set_attribute("db.connection.string", str(conn.engine.url))

SQLAlchemyInstrumentor().instrument(
    engine=engine.sync_engine, # `.sync_engine` is required since this instrumentation does not support the async engine
    before_cursor_execute=add_details,
    after_cursor_execute=add_details,
    dbapi_level_span=True
)
# --- End OpenTelemetry Instrumentation ---
