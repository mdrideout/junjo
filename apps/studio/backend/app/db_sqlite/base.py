"""SQLAlchemy declarative base.

All models inherit from this base.
Pattern from wt_api_v2.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass
