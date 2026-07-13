"""API Key service layer with key generation.

Handles business logic for API key management including secure key generation.
"""

import nanoid

from app.common.audit import AuditAction, AuditResource, audit_log
from app.db_sqlite.api_keys.repository import APIKeyRepository
from app.db_sqlite.api_keys.schemas import APIKeyRead
from app.features.auth.models import AuthenticatedUser


class APIKeyService:
    """Service for API key business logic.

    Static methods to avoid instance state and ensure thread-safety.
    """

    @staticmethod
    def generate_key() -> str:
        """Generate a secure 64-character alphanumeric API key.

        Uses nanoid with alphanumeric alphabet (matches Go implementation).

        Returns:
            64-character alphanumeric string
        """
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return nanoid.generate(alphabet, 64)

    @staticmethod
    def generate_id() -> str:
        """Generate a unique identifier for the API key.

        Uses nanoid with default length (21 characters).

        Returns:
            21-character nanoid
        """
        return nanoid.generate()

    @staticmethod
    async def create_api_key(name: str, authenticated_user: AuthenticatedUser) -> APIKeyRead:
        """Create a new API key.

        Args:
            name: Human-readable name for the key
            authenticated_user: Authenticated user performing the action

        Returns:
            Created API key with generated ID and key value

        Raises:
            SQLAlchemyError: If database operation fails
        """
        # Generate ID and key
        key_id = APIKeyService.generate_id()
        key_value = APIKeyService.generate_key()

        # Audit log at service layer (defense in depth)
        audit_log(
            AuditAction.CREATE,
            AuditResource.API_KEY,
            key_id,
            authenticated_user,
            {"name": name, "key_preview": key_value[:8] + "..."},
        )

        # Save to database
        return await APIKeyRepository.create(
            id=key_id, key=key_value, name=name, authenticated_user=authenticated_user
        )

    @staticmethod
    async def list_api_keys(authenticated_user: AuthenticatedUser) -> list[APIKeyRead]:
        """List all API keys.

        Args:
            authenticated_user: Authenticated user performing the action

        Returns:
            List of all API keys, ordered by created_at descending

        Raises:
            SQLAlchemyError: If database operation fails
        """
        # Audit log at service layer (defense in depth)
        audit_log(AuditAction.LIST, AuditResource.API_KEY, None, authenticated_user)

        return await APIKeyRepository.list_all(authenticated_user=authenticated_user)

    @staticmethod
    async def delete_api_key(id: str, authenticated_user: AuthenticatedUser) -> bool:
        """Delete an API key by ID.

        Args:
            id: API key ID to delete
            authenticated_user: Authenticated user performing the action

        Returns:
            True if key was deleted, False if not found

        Raises:
            SQLAlchemyError: If database operation fails
        """
        # Audit log at service layer (defense in depth)
        audit_log(AuditAction.DELETE, AuditResource.API_KEY, id, authenticated_user)

        return await APIKeyRepository.delete_by_id(id, authenticated_user=authenticated_user)
