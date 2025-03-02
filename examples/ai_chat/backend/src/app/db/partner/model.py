from datetime import datetime

from app.db.base import SQABase
from nanoid import generate
from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column


# SQLAlchemy model
class ContactsTable(SQABase):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(
        String(21), primary_key=True, index=True, default=lambda: generate()
    )
    created_at: Mapped[datetime] = mapped_column(index=True, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(index=True, nullable=False, server_default=func.now())
    gender: Mapped[str]
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]
    age: Mapped[int | None]
    weight_lbs: Mapped[float | None]
    us_state: Mapped[str | None]
    city: Mapped[str | None]
    bio: Mapped[str | None]
