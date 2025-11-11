"""User database model.

Uses modern SQLAlchemy 2.0 syntax with Mapped[] type hints.
"""

from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.datetime_utils import UTCDateTime, utcnow
from app.common.utils import generate_id
from app.db_sqlite.base import Base


class UserTable(Base):
    """User model for authentication.

    Stores user account information including credentials and status.
    """

    __tablename__ = "users"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=lambda: generate_id(size=22)
    )

    # Required fields
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)

    # Password hash (bcrypt)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)

    # Account status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Timestamps - Always UTC with timezone awareness
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
