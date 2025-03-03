from datetime import datetime

from nanoid import generate
from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SQABase


# SQLAlchemy model
class MessagesTable(SQABase):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(21), primary_key=True, index=True, default=lambda: generate())
    created_at: Mapped[datetime] = mapped_column(index=True, nullable=False, server_default=func.now())
    contact_id: Mapped[str] = mapped_column(String(21), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True)
    chat_id: Mapped[str] = mapped_column(String(21), ForeignKey("chats.id", ondelete="CASCADE"), nullable=True)
    message: Mapped[str] = mapped_column(String(2500), nullable=False)
