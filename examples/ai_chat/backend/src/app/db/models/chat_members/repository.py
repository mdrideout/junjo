# app/db/models/chat_members/repository.py

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.db_config import async_session
from app.db.models.chat_members import model, schemas


class ChatMembersRepository:
    @staticmethod
    async def create(chat_member: schemas.ChatMemberCreate) -> schemas.ChatMemberRead:
        """Creates a new chat member record."""
        try:
            db_obj = model.ChatMembersTable(
                chat_id=chat_member.chat_id,
                contact_id=chat_member.contact_id,
            )

            async with async_session() as session:
                session.add(db_obj)
                await session.commit()
                await session.refresh(db_obj)

            return schemas.ChatMemberRead.model_validate(db_obj)
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def read(id: str) -> schemas.ChatMemberRead | None:
        """Reads a chat member record by its ID."""
        try:
            async with async_session() as session:
                stmt = select(model.ChatMembersTable).where(model.ChatMembersTable.id == id)
                db_obj = (await session.execute(stmt)).scalar_one_or_none()
                if db_obj is None:
                    return None
                return schemas.ChatMemberRead.model_validate(db_obj)
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def read_all(skip: int = 0, limit: int = 100) -> list[schemas.ChatMemberRead]:
        """Reads multiple chat member records with pagination."""
        try:
            async with async_session() as session:
                stmt = select(model.ChatMembersTable).offset(skip).limit(limit)
                db_chat_members = (await session.execute(stmt)).scalars().all()
                return [schemas.ChatMemberRead.model_validate(db_chat_member) for db_chat_member in db_chat_members]
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def delete(id: str) -> bool:
        """Deletes a chat member record by its ID."""
        try:
            async with async_session() as session:
                stmt = select(model.ChatMembersTable).where(model.ChatMembersTable.id == id)
                db_chat_member = (await session.execute(stmt)).scalar_one_or_none()
                if db_chat_member is None:
                    return False
                await session.delete(db_chat_member)
                await session.commit()
                return True
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def read_by_chat_id(chat_id: str, skip: int = 0, limit: int = 100) -> list[schemas.ChatMemberRead]:
        """Reads multiple chat member records by chat_id with pagination."""
        try:
            async with async_session() as session:
                stmt = (
                    select(model.ChatMembersTable)
                    .where(model.ChatMembersTable.chat_id == chat_id)
                    .offset(skip)
                    .limit(limit)
                )
                db_chat_members = (await session.execute(stmt)).scalars().all()
                return [schemas.ChatMemberRead.model_validate(db_chat_member) for db_chat_member in db_chat_members]
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def delete_by_chat_id(chat_id: str) -> bool:
        """Deletes a chat member records by its chat_id."""
        try:
            async with async_session() as session:
                stmt = select(model.ChatMembersTable).where(model.ChatMembersTable.chat_id == chat_id)
                db_chat_members = (await session.execute(stmt)).scalars().all()
                if db_chat_members is None:
                    return False
                for member in db_chat_members:
                  await session.delete(member)

                await session.commit()
                return True
        except SQLAlchemyError as e:
            raise e
