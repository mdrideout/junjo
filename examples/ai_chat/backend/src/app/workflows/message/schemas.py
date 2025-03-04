from pydantic import BaseModel


class SendMessageSchema(BaseModel):
    message: str
