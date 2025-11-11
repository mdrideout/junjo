"""API Key database model.

Uses modern SQLAlchemy 2.0 syntax with Mapped[] type hints.
"""

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.datetime_utils import UTCDateTime, utcnow
from app.common.utils import generate_id
from app.db_sqlite.base import Base


class APIKeyTable(Base):
    """API Key model for authentication.

    Stores API keys for authenticating external requests to the ingestion service.
    """

    __tablename__ = "api_keys"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=lambda: generate_id(size=22)
    )

    # Key value (64-char alphanumeric nanoid)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Human-readable name
    name: Mapped[str] = mapped_column(String, nullable=False)

    # Timestamp - Always UTC with timezone awareness
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
