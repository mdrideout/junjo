from pydantic import BaseModel

from app.db.models.chat.schemas import ChatWithMembersRead
from app.db.models.contact.schemas import ContactRead


class CreateSetupContactResponse(BaseModel):
    """Combined data from the contact setup process."""

    contact: ContactRead
    chat_with_members: ChatWithMembersRead
