"""Repository for poller state CRUD operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_sqlite.poller_state.models import PollerState


class PollerStateRepository:
    """Repository for poller state operations.

    This repository manages the single-row poller_state table that tracks
    the last processed ULID key for span ingestion resumption.
    """

    def __init__(self, session: AsyncSession):
        """Initialize repository with async session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def get_last_key(self) -> bytes | None:
        """Get the last processed ULID key.

        Returns:
            Last processed key as bytes, or None if no state exists
            (indicates poller should start from beginning)
        """
        result = await self.session.execute(select(PollerState.last_key).where(PollerState.id == 1))
        return result.scalar_one_or_none()

    async def upsert_last_key(self, last_key: bytes) -> None:
        """Update or insert the last processed key.

        Args:
            last_key: ULID key bytes from ingestion service
        """
        existing = await self.session.get(PollerState, 1)
        if existing:
            existing.last_key = last_key
        else:
            self.session.add(PollerState(id=1, last_key=last_key))

    async def clear_state(self) -> None:
        """Clear poller state (reset to beginning).

        This is useful for manual resets or testing.
        """
        existing = await self.session.get(PollerState, 1)
        if existing:
            existing.last_key = None
