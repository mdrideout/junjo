from datetime import datetime

from nanoid import generate
from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SQABase


# SQLAlchemy model
class ChatsTable(SQABase):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(21), primary_key=True, index=True, default=lambda: generate())
    created_at: Mapped[datetime] = mapped_column(index=True, nullable=False, server_default=func.now())
    last_message_time: Mapped[datetime] = mapped_column(index=True, nullable=True, server_default=func.now())


