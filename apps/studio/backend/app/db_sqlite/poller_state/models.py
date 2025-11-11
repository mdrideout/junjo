"""SQLAlchemy model for poller state persistence."""

from sqlalchemy import CheckConstraint, Column, Integer, LargeBinary

from app.db_sqlite.base import Base


class PollerState(Base):
    """Poller state for span ingestion resumption.

    This is a single-row table (enforced by CHECK constraint) that tracks
    the last processed ULID key from the ingestion service's BadgerDB WAL.

    On startup, the poller reads this key to resume from where it left off.
    After each successful batch, the key is updated.

    Schema matches Go backend: backend/db/schema.sql:21-25
    """

    __tablename__ = "poller_state"

    id = Column(Integer, primary_key=True)
    last_key = Column(LargeBinary, nullable=True)  # ULID bytes, NULL = start from beginning

    __table_args__ = (CheckConstraint("id = 1", name="single_row_check"),)

    def __repr__(self) -> str:
        key_hex = self.last_key.hex() if self.last_key else "None"
        return f"<PollerState(id={self.id}, last_key={key_hex})>"
