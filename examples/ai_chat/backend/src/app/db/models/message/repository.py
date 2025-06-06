# app/db/models/message/repository.py

from sqlalchemy import exists, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import aliased

from app.db.db_config import async_session  # You'll need to define this
from app.db.models.message import model, schemas


class MessageRepository:
    @staticmethod
    async def create(message: schemas.MessageCreate) -> schemas.MessageRead:
        try:
            db_obj = model.MessagesTable(
                contact_id=message.contact_id,
                chat_id=message.chat_id,
                message=message.message,
            )

            async with async_session() as session:
                session.add(db_obj)
                await session.commit()
                await session.refresh(db_obj)

            return schemas.MessageRead.model_validate(db_obj)
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def read(id: str) -> schemas.MessageRead | None:
        try:
            async with async_session() as session:
                stmt = select(model.MessagesTable).where(model.MessagesTable.id == id)
                db_obj = (await session.execute(stmt)).scalar_one_or_none()
                if db_obj is None:
                    return None
                return schemas.MessageRead.model_validate(db_obj)
        except SQLAlchemyError as e:
            raise e


    @staticmethod
    async def read_all(skip: int = 0, limit: int | None = None) -> list[schemas.MessageRead]:
        try:
            async with async_session() as session:
                stmt = select(model.MessagesTable).offset(skip).order_by(model.MessagesTable.created_at.asc())

                if limit is not None:
                    stmt = stmt.limit(limit)

                db_messages = (await session.execute(stmt)).scalars().all()
                return [schemas.MessageRead.model_validate(db_message) for db_message in db_messages]
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def read_all_by_chat_id(chat_id: str, skip: int = 0, limit: int | None = None) -> list[schemas.MessageRead]:
        try:
            async with async_session() as session:
                stmt = (
                    select(model.MessagesTable)
                    .where(model.MessagesTable.chat_id == chat_id)
                    .order_by(model.MessagesTable.created_at.asc())
                    .offset(skip)
                )

                if limit is not None:
                    stmt = stmt.limit(limit)


                db_messages = (await session.execute(stmt)).scalars().all()
                return [
                    schemas.MessageRead.model_validate(db_message)
                    for db_message in db_messages
                ]
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def read_all_by_chat_id_newer_than_message_id(
        chat_id: str,
        message_id: str,
        skip: int = 0,
        limit: int | None = None
    ) -> list[schemas.MessageRead]:
        try:
            async with async_session() as session:
                # Create an alias for the MessagesTable to refer to the message_to_compare_to
                MessagesTableAlias = aliased(model.MessagesTable)

                # Subquery to get the created_at of the comparison message.
                subquery = (
                    select(MessagesTableAlias.created_at)
                    .where(MessagesTableAlias.id == message_id)
                    .scalar_subquery()
                )

                # Check if message_id exists before proceeding.
                exists_stmt = select(exists().where(model.MessagesTable.id == message_id))
                message_exists = await session.execute(exists_stmt)
                if not message_exists.scalar():
                  raise ValueError(f"Message with id {message_id} does not exist")

                # Main query to select messages newer than the subquery result.
                stmt = (
                    select(model.MessagesTable)
                    .where(model.MessagesTable.chat_id == chat_id)
                    .where(model.MessagesTable.created_at > subquery)
                    .order_by(model.MessagesTable.created_at.asc())
                    .offset(skip)
                )

                if limit is not None:
                    stmt = stmt.limit(limit)

                db_messages = (await session.execute(stmt)).scalars().all()
                return [
                    schemas.MessageRead.model_validate(db_message)
                    for db_message in db_messages
                ]
        except SQLAlchemyError as e:
            raise e
        except ValueError as e:
          raise e

    @staticmethod
    async def delete(id: str) -> bool:
        try:
            async with async_session() as session:
                stmt = select(model.MessagesTable).where(model.MessagesTable.id == id)
                db_message = (await session.execute(stmt)).scalar_one_or_none()
                if db_message is None:
                    return False
                await session.delete(db_message)
                await session.commit()
                return True
        except SQLAlchemyError as e:
            raise e

