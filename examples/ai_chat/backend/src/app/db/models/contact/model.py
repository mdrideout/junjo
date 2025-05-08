from datetime import datetime

from nanoid import generate
from sqlalchemy import CheckConstraint, String, func
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SQABase
from app.db.models.contact.schemas import Sex


# SQLAlchemy model
class ContactsTable(SQABase):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(21), primary_key=True, index=True, default=lambda: generate())
    created_at: Mapped[datetime] = mapped_column(index=True, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(index=True, nullable=False, server_default=func.now())

    # Physical attributes
    sex: Mapped[Sex] = mapped_column(SQLAlchemyEnum(Sex), nullable=False)
    age: Mapped[int] = mapped_column(CheckConstraint("age >= 18 AND age <= 150"))
    weight_lbs: Mapped[float] = mapped_column(CheckConstraint("weight_lbs >= 70 AND weight_lbs <= 400"))

    # Personality traits
    openness:          Mapped[float] = mapped_column(CheckConstraint("openness >= 0 AND openness <= 1"))
    conscientiousness: Mapped[float] = mapped_column(CheckConstraint("conscientiousness >= 0 AND conscientiousness <= 1"))  # noqa: E501
    neuroticism:       Mapped[float] = mapped_column(CheckConstraint("neuroticism >= 0 AND neuroticism <= 1"))
    agreeableness:     Mapped[float] = mapped_column(CheckConstraint("agreeableness >= 0 AND agreeableness <= 1"))
    extraversion:      Mapped[float] = mapped_column(CheckConstraint("extraversion >= 0 AND extraversion <= 1"))
    intelligence:      Mapped[float] = mapped_column(CheckConstraint("intelligence >= 0 AND intelligence <= 1"))
    religiousness:     Mapped[float] = mapped_column(CheckConstraint("religiousness >= 0 AND religiousness <= 1"))
    attractiveness:    Mapped[float] = mapped_column(CheckConstraint("attractiveness >= 0 AND attractiveness <= 1"))
    trauma:           Mapped[float] = mapped_column(CheckConstraint("trauma >= 0 AND trauma <= 1"))

    # Location
    latitude: Mapped[float] = mapped_column(CheckConstraint("latitude >= -90 AND latitude <= 90"))
    longitude: Mapped[float] = mapped_column(CheckConstraint("longitude >= -180 AND longitude <= 180"))
    city: Mapped[str]
    state: Mapped[str]

    # Personal information
    first_name: Mapped[str]
    last_name: Mapped[str]
    bio: Mapped[str] = mapped_column(String(2000))
