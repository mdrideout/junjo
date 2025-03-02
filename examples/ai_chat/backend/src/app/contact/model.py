from datetime import datetime

from nanoid import generate
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.contact.schemas import GenderEnum
from app.db.base import SQABase


# SQLAlchemy model
class ContactsTable(SQABase):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(
        String(21), primary_key=True, index=True, default=lambda: generate()
    )
    created_at: Mapped[datetime] = mapped_column(index=True, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(index=True, nullable=False, server_default=func.now())
    gender: Mapped[GenderEnum] = mapped_column(SQLAlchemyEnum(GenderEnum), nullable=False)
    first_name: Mapped[str]
    last_name: Mapped[str]
    age: Mapped[int]
    weight_lbs: Mapped[float]
    us_state: Mapped[str]
    city: Mapped[str]
    bio: Mapped[str]
