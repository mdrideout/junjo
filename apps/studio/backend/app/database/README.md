# Database & Migrations Guide

This document covers database architecture, Alembic migrations, and testing patterns for Junjo AI Studio.

## Table of Contents

1. [Database Architecture](#database-architecture)
2. [Alembic Migration Workflow](#alembic-migration-workflow)
3. [Model Registration Pattern](#model-registration-pattern)
4. [Testing with Autouse Fixtures](#testing-with-autouse-fixtures)
5. [High-Concurrency Patterns](#high-concurrency-patterns)

---

## Database Architecture

### Two Databases, Two Purposes

**SQLite** (`app/db_sqlite/`):
- **Purpose:** Application data (users, API keys, settings)
- **Why SQLite:** Simple, file-based, perfect for structured data
- **Location:** Configurable via `JUNJO_SQLITE_PATH` env var

**SQLite Metadata Index** (`app/db_sqlite/metadata/`):
- **Purpose:** Span metadata index (trace/service → Parquet file paths)
- **Why SQLite:** Fast point lookups with minimal memory usage
- **Location:** Configurable via `JUNJO_METADATA_DB_PATH` env var

**Span storage:**
- **COLD:** Parquet files (from ingestion WAL flushes)
- **HOT:** `hot_snapshot.parquet` (from PrepareHotSnapshot)
- **Queries:** DataFusion scans Parquet directly (no additional embedded analytics DB)

### High-Concurrency Async Pattern

**Critical:** Use async SQLAlchemy throughout the backend for non-blocking I/O.

**Pattern:**
```python
# Each operation gets its own session
async with db_config.async_session() as session:
    async with session.begin():
        result = await session.execute(select(UserTable))
        return result.scalars().first()
```

**Why:**
- Each request gets isolated session
- No session sharing between concurrent requests
- Automatic rollback on errors
- Clean separation of transactions

---

## Alembic Migration Workflow

### What is Alembic?

Alembic is a database migration tool for SQLAlchemy. It:
- Tracks schema version history
- Auto-generates migrations from model changes
- Applies migrations in order
- Supports rollbacks

### Common Workflow

**1. Create or modify a model:**
```python
# app/database/users/models.py
from app.db_sqlite.base import Base
from sqlalchemy import Column, String, DateTime

class UserTable(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
```

**2. Import model in central location:**
```python
# app/database/models.py
from app.database.users.models import UserTable  # noqa: F401
from app.database.api_keys.models import APIKeyTable  # noqa: F401
# Import ALL models here - critical for Alembic
```

**3. Generate migration:**
```bash
cd backend
alembic revision --autogenerate -m "Add users table"
```

**4. Review generated migration:**
```python
# alembic/versions/xxxx_add_users_table.py
def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )

def downgrade() -> None:
    op.drop_table('users')
```

**5. Apply migration:**
```bash
alembic upgrade head
```

### Common Alembic Commands

```bash
# Check current version
alembic current

# Show migration history
alembic history

# Downgrade one version
alembic downgrade -1

# Upgrade to specific version
alembic upgrade <revision_id>

# Show SQL without applying
alembic upgrade head --sql
```

### Alembic Configuration

**Key files:**
- `alembic.ini` - Alembic configuration
- `alembic/env.py` - Environment setup, imports `app/database/models.py`
- `alembic/versions/` - Migration files

---

## Model Registration Pattern

### Why Central Registration Matters

**The Problem:**
- Alembic needs to know about all models to generate migrations
- Test fixtures need to know about all models to create tables
- SQLAlchemy's `Base.metadata` only knows about imported models

**The Solution:**
All SQLAlchemy models MUST be imported in `app/database/models.py`.

### Complete Pattern

**Step 1: Define model in feature directory:**
```python
# app/database/users/models.py
from app.db_sqlite.base import Base
from sqlalchemy import Column, String

class UserTable(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    email = Column(String, nullable=False)
```

**Step 2: Import in central location:**
```python
# app/database/models.py
"""
Central model registration for Alembic and test fixtures.

ALL SQLAlchemy models MUST be imported here.
"""

# Import all models (noqa: F401 disables "unused import" warning)
from app.database.users.models import UserTable  # noqa: F401
from app.database.api_keys.models import APIKeyTable  # noqa: F401
from app.database.ingestion_state.models import IngestionStateTable  # noqa: F401
# Add new models here as they're created
```

**Step 3: Alembic imports from here:**
```python
# alembic/env.py
from app.database.models import *  # Imports all registered models
from app.db_sqlite.base import Base

target_metadata = Base.metadata  # Now includes all models
```

**Step 4: Test fixtures import from here:**
```python
# backend/conftest.py
from app.database.models import *  # Imports all registered models
from app.db_sqlite.base import Base

@pytest.fixture(autouse=True, scope="function")
async def test_db():
    # Base.metadata now includes all models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### What Happens If You Forget?

❌ **Forgot to import model in `models.py`:**
- Alembic won't detect your model
- `alembic revision --autogenerate` won't generate migration
- Test database won't have your table
- Silent failure - hard to debug

✅ **Imported correctly:**
- Alembic sees model changes
- Migrations auto-generated correctly
- Tests get table automatically
- Everything just works

---

## Testing with Autouse Fixtures

### The Autouse Pattern

**Key concept:** Database isolation happens automatically, no explicit `test_db` parameter needed.

**How it works:**
```python
# backend/conftest.py
@pytest.fixture(autouse=True, scope="function")
async def test_db():
    """
    Automatically provides isolated database for each test.

    autouse=True: Runs for every test function automatically
    scope="function": New database for each test (complete isolation)
    """
    # Create temp database file
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    test_db_path = temp_db.name
    temp_db.close()

    # Override database config to use temp file
    original_path = db_config.sqlite_path
    db_config.sqlite_path = test_db_path

    # Create all tables
    async with db_config.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Cleanup
    db_config.sqlite_path = original_path
    await db_config.engine.dispose()
    os.unlink(test_db_path)
```

### Writing Tests (No test_db Parameter)

❌ **Don't do this:**
```python
@pytest.mark.integration
async def test_create_user(test_db):  # DON'T pass test_db
    # ...
```

✅ **Do this:**
```python
@pytest.mark.integration
async def test_create_user():  # No parameter needed
    """Autouse fixture handles database isolation automatically."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/users",
            json={"email": "test@example.com", "password": "password123"}
        )
        assert response.status_code == 200
```

### Why Autouse Fixtures?

**Benefits:**
1. **Less boilerplate:** No `test_db` parameter in every test
2. **Enforced isolation:** Can't forget to use fixture
3. **Cleaner tests:** Focus on behavior, not setup
4. **Co-located tests work:** Fixtures in `backend/conftest.py` apply everywhere

### File-Based vs In-Memory Databases

**We use file-based test databases:**
```python
temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
```

**Why not in-memory (`:memory:`)?**
- In-memory databases don't work with async SQLAlchemy connection pooling
- Each connection gets a different in-memory database
- File-based ensures all connections see same data
- Still fast (temp files cleaned up after each test)

### Critical: conftest.py Location

**Must be at backend/conftest.py** (project root), not `backend/tests/conftest.py`.

**Why:**
- Co-located tests in `app/features/` need access to fixtures
- pytest looks for `conftest.py` in parent directories
- `backend/conftest.py` is parent of both `app/` and `tests/`

---

## High-Concurrency Patterns

### Session-Per-Operation Pattern

**Correct pattern for high concurrency:**

```python
# app/database/users/repository.py
from app.db_sqlite import db_config

class UserRepository:
    @staticmethod
    async def get_by_email(email: str) -> UserTable | None:
        """Each operation creates its own session."""
        async with db_config.async_session() as session:
            result = await session.execute(
                select(UserTable).where(UserTable.email == email)
            )
            return result.scalars().first()

    @staticmethod
    async def create(user_data: dict) -> UserTable:
        """Each operation creates its own session."""
        async with db_config.async_session() as session:
            async with session.begin():  # Auto-commit on success, rollback on error
                user = UserTable(**user_data)
                session.add(user)
                await session.flush()  # Get generated ID
                await session.refresh(user)  # Load relationships
                return user
```

### Why Session-Per-Operation?

**Problem with shared sessions:**
```python
# ❌ BAD: Don't do this
class UserRepository:
    def __init__(self, session):
        self.session = session  # Shared session

    async def get_by_email(self, email: str):
        result = await self.session.execute(...)
        return result.scalars().first()

# What goes wrong:
# - Concurrent requests share session
# - Transaction conflicts
# - Race conditions
# - Difficult to test
```

**Solution: Session-per-operation:**
```python
# ✅ GOOD: Do this
class UserRepository:
    @staticmethod
    async def get_by_email(email: str):
        async with db_config.async_session() as session:
            result = await session.execute(...)
            return result.scalars().first()

# Benefits:
# - Complete isolation between concurrent requests
# - No shared state
# - Automatic cleanup
# - Easy to test
```

### Dynamic Session Access

**Correct:**
```python
# Import the config module, not the session
from app.db_sqlite import db_config

async def get_user():
    async with db_config.async_session() as session:
        # Use session
```

**Incorrect:**
```python
# ❌ Don't import session directly
from app.db_sqlite.db_config import async_session  # Creates session once

async def get_user():
    async with async_session() as session:  # Always uses same session factory
        # This won't work correctly in tests (session points to wrong DB)
```

**Why dynamic access matters:**
- Tests override `db_config.sqlite_path` for temp databases
- Direct imports freeze the session factory to original database
- Dynamic access via `db_config.async_session()` respects overrides

### Transaction Management

**Explicit transactions:**
```python
async with db_config.async_session() as session:
    async with session.begin():
        # All operations in this block are part of one transaction
        user = UserTable(email="test@example.com")
        session.add(user)

        api_key = APIKeyTable(user_id=user.id)
        session.add(api_key)

        # Auto-commit on success, rollback on exception
```

**Auto-commit for single operations:**
```python
async with db_config.async_session() as session:
    # session.begin() not needed for read-only
    result = await session.execute(select(UserTable))
    return result.scalars().all()
```

### Repository Pattern Example

**Complete repository with all patterns:**

```python
# app/database/users/repository.py
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from app.db_sqlite import db_config
from app.database.users.models import UserTable

class UserRepository:
    """User database operations with session-per-operation pattern."""

    @staticmethod
    async def create(email: str, hashed_password: str) -> UserTable:
        """Create new user with automatic ID generation."""
        async with db_config.async_session() as session:
            async with session.begin():
                user = UserTable(
                    id=generate_user_id(),
                    email=email,
                    hashed_password=hashed_password
                )
                session.add(user)
                await session.flush()  # Get ID
                await session.refresh(user)  # Load all columns
                return user

    @staticmethod
    async def get_by_email(email: str) -> UserTable | None:
        """Fetch user by email (read-only)."""
        async with db_config.async_session() as session:
            result = await session.execute(
                select(UserTable).where(UserTable.email == email)
            )
            return result.scalars().first()

    @staticmethod
    async def delete(user_id: str) -> bool:
        """Delete user by ID."""
        async with db_config.async_session() as session:
            async with session.begin():
                result = await session.execute(
                    delete(UserTable).where(UserTable.id == user_id)
                )
                return result.rowcount > 0

    @staticmethod
    async def list_all() -> list[UserTable]:
        """List all users (read-only)."""
        async with db_config.async_session() as session:
            result = await session.execute(select(UserTable))
            return list(result.scalars().all())
```

---

## Common Pitfalls

### Pitfall 1: Forgetting Model Registration

❌ **Problem:**
```python
# Created model but forgot to import in app/database/models.py
# Alembic won't see it, tests won't create table
```

✅ **Solution:**
Always add new models to `app/database/models.py` immediately after creating them.

### Pitfall 2: Shared Session State

❌ **Problem:**
```python
class UserRepository:
    def __init__(self, session):
        self.session = session  # Shared across operations
```

✅ **Solution:**
Use static methods with session-per-operation pattern.

### Pitfall 3: Passing test_db Parameter

❌ **Problem:**
```python
async def test_create_user(test_db):  # Unnecessary
    # ...
```

✅ **Solution:**
Remove parameter, autouse fixture handles it.

### Pitfall 4: Direct Session Import

❌ **Problem:**
```python
from app.db_sqlite.db_config import async_session
async with async_session() as session:  # Won't work in tests
```

✅ **Solution:**
```python
from app.db_sqlite import db_config
async with db_config.async_session() as session:  # Works everywhere
```

---

## Summary

**Database architecture:**
- SQLite for app data + metadata index, Parquet for spans, DataFusion for queries
- Async SQLAlchemy for non-blocking I/O
- Session-per-operation for concurrency

**Alembic workflow:**
1. Modify model in `app/database/{resource}/models.py`
2. Import in `app/database/models.py`
3. Generate: `alembic revision --autogenerate -m "description"`
4. Apply: `alembic upgrade head`

**Testing:**
- Autouse fixture provides automatic isolation
- No `test_db` parameter needed
- `conftest.py` at backend root for co-located tests
- File-based temp databases for async compatibility

**Concurrency:**
- Each operation gets its own session
- Use `async with db_config.async_session() as session:`
- No shared session state
- Explicit transactions with `async with session.begin():`
