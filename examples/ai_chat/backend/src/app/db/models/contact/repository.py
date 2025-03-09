from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.db_config import async_session  # You'll need to define this
from app.db.models.contact import model, schemas


class ContactRepository:
    # Should only be created through setup function
    # @staticmethod
    # async def create(contact: schemas.ContactCreate) -> schemas.ContactRead:
    #     """
    #     Creats a new contact in the database.
    #     """
    #     try:
    #         db_obj = model.ContactsTable(
    #             gender=contact.gender,
    #             first_name=contact.first_name,
    #             last_name=contact.last_name,
    #             age=contact.age,
    #             weight_lbs=contact.weight_lbs,
    #             us_state=contact.us_state,
    #             city=contact.city,
    #             bio=contact.bio,
    #         )

    #         async with async_session() as session:
    #             session.add(db_obj)
    #             await session.commit()
    #             await session.refresh(db_obj)

    #         return schemas.ContactRead.model_validate(db_obj)
    #     except SQLAlchemyError as e:
    #         raise e

    @staticmethod
    async def read(id: str) -> schemas.ContactRead | None:
        try:
            async with async_session() as session:
                stmt = select(model.ContactsTable).where(model.ContactsTable.id == id)
                db_obj = (await session.execute(stmt)).scalar_one_or_none()
                if db_obj is None:
                    return None
                return schemas.ContactRead.model_validate(db_obj)
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def read_all(skip: int = 0, limit: int = 100) -> list[schemas.ContactRead]:
        try:
            async with async_session() as session:
                stmt = select(model.ContactsTable).offset(skip).limit(limit)
                db_contacts = (await session.execute(stmt)).scalars().all()
                return [schemas.ContactRead.model_validate(db_contact) for db_contact in db_contacts]
        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def delete(id: str) -> bool:
        try:
            async with async_session() as session:
                stmt = select(model.ContactsTable).where(model.ContactsTable.id == id)
                db_contact = (await session.execute(stmt)).scalar_one_or_none()
                if db_contact is None:
                    return False
                await session.delete(db_contact)
                await session.commit()
                return True
        except SQLAlchemyError as e:
            raise e
