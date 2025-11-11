"""UTC datetime utilities for consistent timezone handling across the application.

This module provides:
1. Custom SQLAlchemy type that enforces UTC and stores as ISO 8601 with 'Z'
2. Utility functions for datetime operations
3. Type validation for timezone-aware datetimes

Usage:
    from app.common.datetime_utils import UTCDateTime, utcnow

    # In SQLAlchemy models:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    # In Python code:
    now = utcnow()  # Always returns timezone-aware UTC datetime
"""

from datetime import UTC, datetime

from sqlalchemy import String, TypeDecorator


class UTCDateTime(TypeDecorator):
    """SQLAlchemy type that enforces UTC timestamps.

    Storage:
        SQLite: ISO 8601 string with 'Z' suffix stored as TEXT (e.g., '2025-01-15T10:30:00Z')

    Python:
        Always returns timezone-aware datetime objects in UTC.
        Rejects naive datetimes on input.

    Benefits:
        1. Stores explicit timezone ('Z') in database as text
        2. Prevents naive datetimes from being stored
        3. Automatic conversion on read/write
        4. No ambiguity about timezone
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> str | None:
        """Convert Python datetime to database format.

        Args:
            value: Timezone-aware datetime or None

        Returns:
            ISO 8601 string with 'Z' suffix, or None

        Raises:
            ValueError: If datetime is naive (no timezone)
        """
        if value is None:
            return None

        if value.tzinfo is None:
            raise ValueError(
                f"Naive datetime not allowed: {value}. "
                "Use datetime.now(UTC) or utcnow() instead of datetime.now()."
            )

        # Convert to UTC if not already
        utc_value = value.astimezone(UTC)

        # Store as ISO 8601 with 'Z' suffix (explicit UTC)
        # Format: 2025-01-15T10:30:00Z (no microseconds for simplicity)
        return utc_value.strftime("%Y-%m-%dT%H:%M:%SZ")

    def process_result_value(self, value: str | None, dialect) -> datetime | None:
        """Convert database format to Python datetime.

        Args:
            value: ISO 8601 string from database

        Returns:
            Timezone-aware datetime in UTC, or None
        """
        if value is None:
            return None

        # Handle both 'Z' suffix and '+00:00' formats
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        # Parse and ensure UTC
        dt = datetime.fromisoformat(value)
        return dt.astimezone(UTC)


def utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime.

    Use this instead of datetime.now() or datetime.utcnow().

    Returns:
        Current time in UTC with timezone information.
    """
    return datetime.now(UTC)


def validate_aware_datetime(dt: datetime) -> datetime:
    """Validate that datetime is timezone-aware.

    Args:
        dt: Datetime to validate

    Returns:
        The same datetime if valid

    Raises:
        ValueError: If datetime is naive
    """
    if dt.tzinfo is None:
        raise ValueError(
            f"Naive datetime not allowed: {dt}. "
            "All datetimes must be timezone-aware (use datetime.now(UTC) or utcnow())."
        )
    return dt


def format_iso8601_utc(dt: datetime) -> str:
    """Format datetime as ISO 8601 with 'Z' suffix.

    Args:
        dt: Timezone-aware datetime

    Returns:
        ISO 8601 string with 'Z' suffix (e.g., '2025-01-15T10:30:00Z')

    Raises:
        ValueError: If datetime is naive
    """
    validate_aware_datetime(dt)
    utc_dt = dt.astimezone(UTC)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
