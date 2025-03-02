from datetime import datetime

from app.db.base import SQABase
from app.db.models.contact.schemas import GenderEnum
from nanoid import generate
from sqlalchemy import CheckConstraint, String, func
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column


# SQLAlchemy model
class ContactsTable(SQABase):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(21), primary_key=True, index=True, default=lambda: generate())
    created_at: Mapped[datetime] = mapped_column(index=True, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(index=True, nullable=False, server_default=func.now())
    gender: Mapped[GenderEnum] = mapped_column(SQLAlchemyEnum(GenderEnum), nullable=False)
    first_name: Mapped[str]
    last_name: Mapped[str]
    age: Mapped[int] = mapped_column(CheckConstraint("age >= 18 AND age <= 150"))
    weight_lbs: Mapped[float] = mapped_column(CheckConstraint("weight_lbs >= 70 AND weight_lbs <= 850"))
    us_state: Mapped[str]
    city: Mapped[str]
    bio: Mapped[str] = mapped_column(String(1000))
