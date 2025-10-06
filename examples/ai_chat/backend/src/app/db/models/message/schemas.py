# app/db/models/message/schemas.py

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageCreate(BaseModel):
    chat_id: str
    contact_id: str | None
    message: str
    image_id: str | None = None


class MessageRead(BaseModel):
    id: str
    created_at: datetime
    contact_id: str | None
    chat_id: str
    message: str
    image_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MessageDelete(BaseModel):
    id: str
