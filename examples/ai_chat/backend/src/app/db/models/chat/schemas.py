# app/db/models/chat/schemas.py

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models.chat_members.schemas import ChatMemberRead


class ChatCreate(BaseModel):
    pass

class ChatRead(BaseModel):
    id: str
    created_at: datetime
    last_message_time: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatDelete(BaseModel):
    id: str


class ChatWithMembersRead(ChatRead):
    id: str
    members: list[ChatMemberRead] = []

    model_config = ConfigDict(from_attributes=True)
