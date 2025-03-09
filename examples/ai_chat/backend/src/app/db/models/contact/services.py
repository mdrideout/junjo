from app.db.models.chat_members.repository import ChatMembersRepository
from app.db.models.contact.repository import ContactRepository
from app.db.models.contact.schemas import ContactRead


class ContactService:
    """Service layer for contact related business logic."""

    @staticmethod
    async def get_chat_contact(chat_id: str) -> ContactRead:
        """
        Business logic to handle getting the chat contact from the database.

        Currently only returns the first contact found.
        """

        # Get the contacts in this chat
        chat_contacts = await ChatMembersRepository.read_by_chat_id(chat_id)
        if not chat_contacts:
            raise ValueError("No contacts found in this chat.")

        contact_id = chat_contacts[0].contact_id
        if not contact_id:
            raise ValueError("Contact id could not be isolated from chat members.")

        contact = await ContactRepository.read(contact_id)
        if not contact:
            raise ValueError("Contact could not be found.")

        return contact
