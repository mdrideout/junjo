"""API Key repository using high-concurrency pattern.

Each method creates its own session for complete isolation.
See: PYTHON_BACKEND_HIGH_CONCURRENCY_DB_PATTERN.md
"""

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.common.audit import AuditAction, AuditResource, audit_log
from app.db_sqlite import db_config
from app.db_sqlite.api_keys.models import APIKeyTable
from app.db_sqlite.api_keys.schemas import APIKeyRead
from app.features.auth.models import AuthenticatedUser


class APIKeyRepository:
    """Repository for API key database operations.

    All methods are static to avoid instance state and ensure thread-safety.
    Each method creates its own database session for complete isolation.
    """

    @staticmethod
    async def create(
        id: str, key: str, name: str, authenticated_user: AuthenticatedUser
    ) -> APIKeyRead:
        """Create a new API key.

        Args:
            id: Unique identifier for the key (nanoid)
            key: API key value (64-char alphanumeric nanoid)
            name: Human-readable name
            authenticated_user: Authenticated user performing the action

        Returns:
            Created API key

        Raises:
            SQLAlchemyError: If database operation fails

        Pattern:
            1. Create session
            2. Add object
            3. Commit
            4. Refresh (load generated fields)
            5. Validate to Pydantic BEFORE session closes
        """
        # Audit log at repository layer (defense in depth - database operation)
        audit_log(
            AuditAction.DB_INSERT, AuditResource.API_KEY, id, authenticated_user, {"name": name}
        )

        try:
            db_obj = APIKeyTable(id=id, key=key, name=name)

            async with db_config.async_session() as session:
                session.add(db_obj)
                await session.commit()
                await session.refresh(db_obj)

                # Validate to Pydantic before session closes
                return APIKeyRead.model_validate(db_obj)

        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def list_all(authenticated_user: AuthenticatedUser) -> list[APIKeyRead]:
        """List all API keys, ordered by created_at descending.

        Args:
            authenticated_user: Authenticated user performing the action

        Returns:
            List of all API keys

        Raises:
            SQLAlchemyError: If database operation fails
        """
        # Audit log at repository layer (defense in depth - database operation)
        audit_log(AuditAction.DB_QUERY, AuditResource.API_KEY, None, authenticated_user)

        try:
            async with db_config.async_session() as session:
                stmt = select(APIKeyTable).order_by(APIKeyTable.created_at.desc())
                result = await session.execute(stmt)
                db_objs = result.scalars().all()

                # Validate with Pydantic before session closes
                return [APIKeyRead.model_validate(obj) for obj in db_objs]

        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def get_by_id(id: str) -> APIKeyRead | None:
        """Get API key by ID.

        Args:
            id: Unique identifier

        Returns:
            API key if found, None otherwise

        Raises:
            SQLAlchemyError: If database operation fails
        """
        try:
            async with db_config.async_session() as session:
                stmt = select(APIKeyTable).where(APIKeyTable.id == id)
                result = await session.execute(stmt)
                db_obj = result.scalar_one_or_none()

                if db_obj:
                    return APIKeyRead.model_validate(db_obj)
                return None

        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def get_by_key(key: str) -> APIKeyRead | None:
        """Get API key by key value (for authentication).

        Args:
            key: API key value

        Returns:
            API key if found, None otherwise

        Raises:
            SQLAlchemyError: If database operation fails
        """
        try:
            async with db_config.async_session() as session:
                stmt = select(APIKeyTable).where(APIKeyTable.key == key)
                result = await session.execute(stmt)
                db_obj = result.scalar_one_or_none()

                if db_obj:
                    return APIKeyRead.model_validate(db_obj)
                return None

        except SQLAlchemyError as e:
            raise e

    @staticmethod
    async def delete_by_id(id: str, authenticated_user: AuthenticatedUser) -> bool:
        """Delete an API key by ID.

        Args:
            id: API key ID to delete
            authenticated_user: Authenticated user performing the action

        Returns:
            True if key was deleted, False if key not found

        Raises:
            SQLAlchemyError: If database operation fails
        """
        # Audit log at repository layer (defense in depth - database operation)
        audit_log(AuditAction.DB_DELETE, AuditResource.API_KEY, id, authenticated_user)

        try:
            async with db_config.async_session() as session:
                stmt = delete(APIKeyTable).where(APIKeyTable.id == id)
                result = await session.execute(stmt)
                await session.commit()

                # Check if any rows were deleted
                return result.rowcount > 0

        except SQLAlchemyError as e:
            raise e
