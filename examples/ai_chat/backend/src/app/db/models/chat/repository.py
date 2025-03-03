# app/db/models/chat/repository.py

from sqlalchemy import join, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.db_config import async_session
from app.db.models.chat import model, schemas
from app.db.models.chat_members.model import ChatMembersTable


class ChatRepository:
    @staticmethod
    async def create() -> schemas.ChatRead:
        """Creates a new chat record."""
        try:
            db_obj = model.ChatsTable()  # No need for constructor args as only has defaults

            async with async_session() as session:
                session.add(db_obj)
                await session.commit()
                await session.refresh(db_obj)

            return schemas.ChatRead.model_validate(db_obj)
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def read(id: str) -> schemas.ChatRead | None:
        """Reads a chat record by its ID."""
        try:
            async with async_session() as session:
                stmt = select(model.ChatsTable).where(model.ChatsTable.id == id)
                db_obj = (await session.execute(stmt)).scalar_one_or_none()
                if db_obj is None:
                    return None
                return schemas.ChatRead.model_validate(db_obj)
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def read_all(skip: int = 0, limit: int = 100) -> list[schemas.ChatRead]:
        """Reads multiple chat records with pagination."""
        try:
            async with async_session() as session:
                stmt = select(model.ChatsTable).offset(skip).limit(limit)
                db_chats = (await session.execute(stmt)).scalars().all()
                return [schemas.ChatRead.model_validate(db_chat) for db_chat in db_chats]
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def delete(id: str) -> bool:
        """Deletes a chat record by its ID."""
        try:
            async with async_session() as session:
                stmt = select(model.ChatsTable).where(model.ChatsTable.id == id)
                db_chat = (await session.execute(stmt)).scalar_one_or_none()
                if db_chat is None:
                    return False
                await session.delete(db_chat)
                await session.commit()
                return True
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def read_all_with_members(skip: int = 0, limit: int = 100) -> list[schemas.ChatWithMembersRead]:
        """Reads all chats, including their members using explicit joins."""
        try:
            async with async_session() as session:
                # Explicit join between ChatsTable and ChatMembersTable
                joined_stmt = join(
                    model.ChatsTable,
                    ChatMembersTable,
                    model.ChatsTable.id == ChatMembersTable.chat_id,
                    isouter=True,  # Use an outer join to get all chats even without members
                )

                # Select the columns we need from both tables
                stmt = (
                    select(model.ChatsTable, ChatMembersTable)
                    .select_from(joined_stmt)
                    .offset(skip)
                    .limit(limit)
                    .order_by(model.ChatsTable.last_message_time.desc())
                )

                results = (await session.execute(stmt)).all()

                # Group the results by chat ID and build the response
                chat_data = {}
                for chat, member in results:
                    if chat.id not in chat_data:
                        chat_data[chat.id] = schemas.ChatWithMembersRead.model_validate(chat)
                    if member:  # Check if member is not None (due to outer join)
                        chat_data[chat.id].members.append(schemas.ChatMemberRead.model_validate(member))

                return list(chat_data.values())
        except SQLAlchemyError as e:
            raise e
