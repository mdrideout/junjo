from pydantic import BaseModel

from app.db.models.contact.schemas import GenderEnum


class ContactCreateWorkflowRequest(BaseModel):
    gender: GenderEnum
