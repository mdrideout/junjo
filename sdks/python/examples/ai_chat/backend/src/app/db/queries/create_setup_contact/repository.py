from sqlalchemy import exc

from app.db.db_config import async_session
from app.db.models.chat.model import ChatsTable
from app.db.models.chat.schemas import ChatRead, ChatWithMembersRead
from app.db.models.chat_members.model import ChatMembersTable
from app.db.models.chat_members.schemas import ChatMemberRead
from app.db.models.contact.model import ContactsTable
from app.db.models.contact.schemas import ContactCreate, ContactRead
from app.db.queries.create_setup_contact.schemas import CreateSetupContactResponse


class CreateSetupContactRepository:
    @staticmethod
    async def create_setup_contact(contact: ContactCreate) -> CreateSetupContactResponse:
        """
        Create and setup a new contact.
        - Creates the contact
        - Sets up a new chat with the contact
        - Adds the new contact to the chat

        This takes place within a single database transaction to ensure data integrity.
        """
        async with async_session() as session:
            try:
                async with session.begin():
                    # 1. Create the contact
                    db_contact = ContactsTable(**contact.model_dump())
                    session.add(db_contact)
                    await session.flush()

                    # 2. Create the chat
                    db_chat = ChatsTable()
                    session.add(db_chat)
                    await session.flush()

                    # 3. Create the chat membership
                    db_chat_member = ChatMembersTable(
                        chat_id=db_chat.id,
                        contact_id=db_contact.id,
                    )
                    session.add(db_chat_member)
                    await session.flush()

                    # --- Construct the ChatWithMembersRead object ---
                    contact_read = ContactRead.model_validate(db_contact)
                    chat_read = ChatRead.model_validate(db_chat)
                    member_read = ChatMemberRead.model_validate(db_chat_member)

                    chat_with_members = ChatWithMembersRead(
                        id=chat_read.id,
                        created_at=chat_read.created_at,
                        last_message_time=chat_read.last_message_time,
                        members=[member_read],  # Include the member
                    )

                    response = CreateSetupContactResponse(
                        contact=contact_read,
                        chat_with_members=chat_with_members,
                    )

                    return response

            except exc.SQLAlchemyError:
                await session.rollback()
                raise  # Re-raise the exception
