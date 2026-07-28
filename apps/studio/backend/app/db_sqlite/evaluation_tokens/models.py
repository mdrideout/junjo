"""SQLAlchemy model for separately scoped evaluation-control tokens."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.datetime_utils import UTCDateTime, utcnow
from app.common.utils import generate_id
from app.db_sqlite.base import Base

MAX_TOKEN_NAME_BYTES = 256
MAX_TOKEN_PREFIX_BYTES = 32


class EvaluationTokenTable(Base):
    """One revocable control/query credential with no stored plaintext secret."""

    __tablename__ = "evaluation_tokens"
    __table_args__ = (
        CheckConstraint(
            f"length(CAST(name AS BLOB)) BETWEEN 1 AND {MAX_TOKEN_NAME_BYTES}",
            name="evaluation_tokens_name_bytes",
        ),
        CheckConstraint(
            f"length(CAST(prefix AS BLOB)) BETWEEN 1 AND {MAX_TOKEN_PREFIX_BYTES}",
            name="evaluation_tokens_prefix_bytes",
        ),
        CheckConstraint(
            "length(secret_hash) = 64",
            name="evaluation_tokens_secret_hash_length",
        ),
        CheckConstraint(
            "evaluation_read = 1 OR evaluation_write = 1 OR evidence_read = 1",
            name="evaluation_tokens_has_scope",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(22),
        primary_key=True,
        default=lambda: generate_id(size=22),
    )
    name: Mapped[str] = mapped_column(String(MAX_TOKEN_NAME_BYTES), nullable=False)
    prefix: Mapped[str] = mapped_column(
        String(MAX_TOKEN_PREFIX_BYTES),
        nullable=False,
        unique=True,
        index=True,
    )
    secret_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    evaluation_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evaluation_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(22),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utcnow,
    )
