from datetime import datetime

from nanoid import generate
from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SQABase


# SQLAlchemy model
class ChatMembersTable(SQABase):
    __tablename__ = "chat_members"

    id: Mapped[str] = mapped_column(String(21), primary_key=True, index=True, default=lambda: generate())
    joined_at: Mapped[datetime] = mapped_column(index=True, nullable=False, server_default=func.now())
    chat_id: Mapped[str] = mapped_column(String(21), ForeignKey("chats.id", ondelete="CASCADE"),  nullable=True)
    contact_id: Mapped[str] = mapped_column(String(21), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True)
