# Database Layer - Asyncio-Safe SQLite Implementation

This directory contains the database layer for the Junjo Python backend, implementing an asyncio-safe, high-concurrency pattern for SQLite operations.

## Architecture Overview

```
app/db_sqlite/
├── base.py                    # SQLAlchemy declarative base
├── db_config.py              # Engine & session factory (CRITICAL - READ BELOW)
└── users/
    ├── models.py             # SQLAlchemy model
    ├── schemas.py            # Pydantic schemas
    └── repository.py         # Data access layer
```

## Critical Implementation Details

### 1. Production Database Configuration (`db_config.py`)

**Pattern: Eager Initialization**
```python
# Engine is created at MODULE IMPORT TIME
engine = create_async_engine(
    settings.database.sqlite_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},  # Required for async
)

async_session = async_sessionmaker(engine, expire_on_commit=False)
```

**⚠️ IMPORTANT:**
- Engine creation is **eager** (not lazy) - matches wt_api_v2 production pattern
- Simple, clean code - no mutable globals or complex factory functions
- SQLite-specific PRAGMA settings applied on every connection:
  - `PRAGMA foreign_keys=ON` - Enable FK constraints (off by default)
  - `PRAGMA journal_mode=WAL` - Write-Ahead Logging for concurrency
  - `PRAGMA synchronous=NORMAL` - Balance safety/performance

**Why Not Lazy Initialization?**
- Lazy initialization with mutable globals is an antipattern
- Adds unnecessary complexity
- Production code from wt_api_v2 proves eager initialization works reliably
- Tests handle isolation via environment variables (see below)

### 2. Repository Pattern - High Concurrency

**Pattern: Static Methods with Per-Operation Sessions**

```python
class UserRepository:
    @staticmethod
    async def create(email: str, password_hash: str) -> UserRead:
        async with db_config.async_session() as session:  # New session per call
            db_obj = UserTable(email=email, password_hash=password_hash)
            session.add(db_obj)
            await session.commit()
            await session.refresh(db_obj)
            return UserRead.model_validate(db_obj)  # Validate BEFORE session closes
```

**Critical Points:**
1. **Dynamic access**: `db_config.async_session()` not `from db_config import async_session`
   - Allows test fixtures to override the session factory
   - Avoids stale module-level imports

2. **`expire_on_commit=False`**: **REQUIRED** for async safety
   - Prevents lazy-loading errors when accessing objects after commit
   - Validated pattern from wt_api_v2

3. **Validate to Pydantic before session closes**:
   - Convert SQLAlchemy objects to Pydantic immediately
   - Prevents detached instance errors

4. **Each method creates its own session**:
   - Complete isolation between operations
   - Thread-safe and asyncio-safe
   - No shared state between concurrent requests

### 3. SQLite Specifics

**WAL Mode (Write-Ahead Logging)**
```python
cursor.execute("PRAGMA journal_mode=WAL")
```
- Allows concurrent reads during writes
- Better performance for async operations
- **IMPORTANT**: Call `checkpoint_wal()` on app shutdown to flush WAL to main DB

**Foreign Keys**
```python
cursor.execute("PRAGMA foreign_keys=ON")
```
- **OFF by default in SQLite** - must enable explicitly
- Ensures referential integrity

**Check Same Thread: False**
```python
connect_args={"check_same_thread": False}
```
- Required for async SQLite operations
- SQLite default is single-threaded, this allows async event loop usage

## Testing Strategy - Critical for Avoiding Regressions

### Why File-Based Test Databases (Not `:memory:`)

**Problem with `:memory:` databases:**
1. **Connection-specific**: Each connection sees a different database
2. **Alembic migrations fail**: Batch operations need file-based DB
3. **WAL mode incompatible**: Cannot use `PRAGMA journal_mode=WAL` with `:memory:`
4. **Connection pooling issues**: Async engine may create multiple connections

**✅ Solution: Temporary File-Based Databases**

### Test Configuration (`tests/conftest.py`)

**Step 1: Set Environment Variable BEFORE Any Imports**
```python
import os
import tempfile

# CRITICAL: Set BEFORE importing app code
_test_base_dir = tempfile.mkdtemp(prefix="junjo_test_")
os.environ["JUNJO_SQLITE_PATH"] = f"{_test_base_dir}/production_stub.db"

# NOW safe to import (db_config will use test path)
from app.database.base import Base
```

**Why this works:**
- `db_config.py` creates engine at import time using `settings.database.sqlite_url`
- By setting env var first, engine points to test location, not production
- Production code stays simple (no lazy loading needed)

**Step 2: Per-Test Isolated Databases**
```python
@pytest_asyncio.fixture(scope="function", autouse=True)
async def test_db():
    # Each test gets its own temp DB file
    temp_dir = tempfile.mkdtemp(prefix="test_db_")
    db_path = os.path.join(temp_dir, "test.db")

    # Create engine & schema
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Override global session with test session
    db_config.async_session = async_sessionmaker(engine, expire_on_commit=False)
```

**Test Database Locations:**
- Production stub: `/tmp/junjo_test_xxxxx/production_stub.db` (never actually used)
- Per-test DBs: `/tmp/test_db_xxxxx/test.db` (one per test, auto-cleaned)

### Common Pitfalls to Avoid

❌ **DON'T: Import `async_session` directly in repositories**
```python
from app.database.db_config import async_session  # Wrong!
```
This creates a module-level reference that test fixtures can't override.

✅ **DO: Use dynamic access**
```python
from app.database import db_config

async with db_config.async_session() as session:  # Correct!
```

❌ **DON'T: Try to use `:memory:` databases with Alembic**
```python
os.environ["JUNJO_SQLITE_PATH"] = ":memory:"  # Will fail!
```

✅ **DO: Use temporary file paths**
```python
os.environ["JUNJO_SQLITE_PATH"] = f"{tempfile.mkdtemp()}/test.db"
```

❌ **DON'T: Create lazy initialization with mutable globals**
```python
_engine = None  # Antipattern!
def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(...)
```

✅ **DO: Keep production code simple with eager initialization**
```python
engine = create_async_engine(...)  # Simple, clean, validated pattern
```

❌ **DON'T: Worry about `# type: ignore` on `result.rowcount`**
```python
result = await session.execute(delete_stmt)
return result.rowcount  # type: ignore[union-attr]  # This is CORRECT
```
These type ignore comments are **not** gitignore - they're directives for Python's static type checker (Pylance/Pyright).

**Why they're needed:**
- `AsyncSession.execute()` returns `Result[Any]` (generic type)
- For DELETE/UPDATE statements, the actual object has `rowcount` attribute
- The type system can't statically prove this, even though it's guaranteed by SQLAlchemy
- Accessing `result.rowcount` directly is the [documented SQLAlchemy pattern](https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.CursorResult.rowcount)

**Runtime guarantee:**
Per PEP 249 and SQLAlchemy docs, all DBAPIs must support `rowcount` for UPDATE/DELETE statements. The attribute will always exist - the type ignore is just working around a type system limitation.

## Database Storage Locations

### Development/Local
```
.dbdata/
├── sqlite/
│   └── junjo.db              # Application database
├── duckdb/
│   └── traces.duckdb         # Analytics data
└── badgerdb/                 # Ingestion service data
```

### Docker
```
Container path: /dbdata/sqlite/junjo.db
Host mount: ./.dbdata → /dbdata
```

### Tests
```
System temp: /var/folders/.../test_db_xxxxx/test.db
- Isolated per test
- Auto-cleaned after test completes
- Full schema via Base.metadata.create_all()
```

## Migrations (Alembic)

**Generate Migration:**
```bash
uv run alembic revision --autogenerate -m "Description"
```

**Apply Migrations:**
```bash
uv run alembic upgrade head
```

**Critical for Alembic:**
- All models must be imported in `app/database/__init__.py`
- Alembic's `env.py` uses `render_as_batch=True` for SQLite ALTER TABLE support
- Migrations require file-based database (temporary files work fine)

## OpenTelemetry Integration

SQLAlchemy operations are automatically instrumented via:
```python
SQLAlchemyInstrumentor().instrument(
    engine=engine.sync_engine,
    enable_commenter=True,
)
```

This provides:
- SQL query tracing
- Performance metrics
- Query comment annotations

## Migration from Go Backend

This Python implementation mirrors the validated patterns from:
- `wt_api_v2`: High-concurrency async repository pattern
- Go backend: Database storage structure in `.dbdata/`

**Key Differences:**
- Go: Synchronous SQLite with connection pooling
- Python: Async SQLite with WAL mode and `check_same_thread=False`

## References

- [PYTHON_BACKEND_HIGH_CONCURRENCY_DB_PATTERN.md](../../PYTHON_BACKEND_HIGH_CONCURRENCY_DB_PATTERN.md)
- [SQLAlchemy 2.0 Async Docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)
- [Alembic Batch Operations](https://alembic.sqlalchemy.org/en/latest/batch.html)
