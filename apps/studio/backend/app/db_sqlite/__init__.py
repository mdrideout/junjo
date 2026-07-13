"""Database package.

Imports all models so Alembic can detect them for autogenerate.

IMPORTANT: Every new model must be imported here for Alembic to work.
"""

# Import base first
from app.db_sqlite.base import Base  # noqa: F401

# Import all models (order matters for foreign keys)
from app.db_sqlite.users.models import UserTable  # noqa: F401

# Add future models here:
# from app.database.api_keys.models import APIKeyTable  # noqa: F401
