# app/db/models/chat_members/schemas.py

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatMemberCreate(BaseModel):
    chat_id: str
    contact_id: str


class ChatMemberRead(BaseModel):
    id: str
    joined_at: datetime
    chat_id: str | None
    contact_id: str | None

    model_config = ConfigDict(from_attributes=True)


class ChatMemberDelete(BaseModel):
    id: str
