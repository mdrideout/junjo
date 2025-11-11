"""Alembic environment configuration.

Async-compatible migration runner with SQLite-specific settings.
Pattern from wt_api_v2 (validated for production).

SQLite-specific:
- render_as_batch=True (required for ALTER TABLE support)
- Direct model imports (not package import)
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import settings to get database URL
from app.config.settings import settings

# Import Base to get metadata
from app.db_sqlite.base import Base

# Import all models DIRECTLY (CRITICAL - ensures Alembic sees all tables)
# Add new models here as they are created
from app.db_sqlite.users.models import UserTable  # noqa: F401

# Future models:
# from app.database.api_keys.models import APIKeyTable  # noqa: F401

# Alembic Config object
config = context.config

# Interpret config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata from Base
target_metadata = Base.metadata

# Set naming convention for constraints
target_metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL script without connecting to database.
    """
    url = settings.database.sqlite_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations with provided connection.

    Args:
        connection: SQLAlchemy connection to use for migrations

    IMPORTANT: render_as_batch=True is REQUIRED for SQLite.
    SQLite has limited ALTER TABLE support. Batch mode creates
    a new table, copies data, and swaps tables to work around this.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True  # ⚠️ REQUIRED for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine.

    Creates engine and runs migrations asynchronously.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.database.sqlite_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
