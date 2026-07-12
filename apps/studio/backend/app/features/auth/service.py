"""
Authentication service layer.

Contains business logic for authentication operations.
"""

from app.common.audit import AuditAction, AuditResource, audit_log
from app.db_sqlite.users.repository import UserRepository
from app.db_sqlite.users.schemas import UserRead
from app.features.auth.models import AuthenticatedUser
from app.features.auth.utils import hash_password, verify_password


class AuthService:
    """Service for authentication operations."""

    @staticmethod
    async def db_has_users() -> bool:
        """
        Check if any users exist.

        Returns:
            True if users exist, False otherwise
        """
        return await UserRepository.db_has_users()

    @staticmethod
    async def create_first_user(email: str, password: str) -> UserRead:
        """
        Create the first user (only allowed if no users exist).

        Uses atomic transaction with SELECT FOR UPDATE to prevent race conditions.

        Args:
            email: User email
            password: Plain text password

        Returns:
            Created user

        Raises:
            ValueError: If users already exist
            IntegrityError: If email already exists
        """
        # Hash password
        hashed_password = hash_password(password)

        # Use atomic method that checks and creates in a single transaction
        # This prevents race conditions when multiple requests try to create first user
        return await UserRepository.create_first_user_atomic(
            email=email, password_hash=hashed_password
        )

    @staticmethod
    async def create_user(
        email: str, password: str, authenticated_user: AuthenticatedUser
    ) -> UserRead:
        """
        Create a new user.

        Args:
            email: User email
            password: Plain text password
            authenticated_user: Authenticated user performing the action

        Returns:
            Created user

        Raises:
            IntegrityError: If email already exists
        """
        # Audit log at service layer (defense in depth)
        audit_log(
            AuditAction.CREATE, AuditResource.USER, None, authenticated_user, {"email": email}
        )

        hashed_password = hash_password(password)
        return await UserRepository.create(
            email=email, password_hash=hashed_password, authenticated_user=authenticated_user
        )

    @staticmethod
    async def validate_credentials(email: str, password: str) -> UserRead | None:
        """
        Validate user credentials.

        Args:
            email: User email
            password: Plain text password

        Returns:
            User if credentials are valid, None otherwise
        """
        # Get user with password hash
        user_with_password = await UserRepository.get_by_email(email)
        if user_with_password is None:
            return None

        # Verify password
        if not verify_password(password, user_with_password.password_hash):
            return None

        # Return user without password hash
        user = await UserRepository.get_by_id(user_with_password.id)
        return user

    @staticmethod
    async def list_users(authenticated_user: AuthenticatedUser) -> list[UserRead]:
        """
        List all users.

        Args:
            authenticated_user: Authenticated user performing the action

        Returns:
            List of all users
        """
        # Audit log at service layer (defense in depth)
        audit_log(AuditAction.LIST, AuditResource.USER, None, authenticated_user)

        return await UserRepository.list_users(authenticated_user=authenticated_user)

    @staticmethod
    async def delete_user(user_id: str, authenticated_user: AuthenticatedUser) -> bool:
        """
        Delete a user.

        Args:
            user_id: User ID to delete
            authenticated_user: Authenticated user performing the action

        Returns:
            True if user was deleted, False if not found
        """
        # Audit log at service layer (defense in depth)
        audit_log(AuditAction.DELETE, AuditResource.USER, user_id, authenticated_user)

        return await UserRepository.delete_user(user_id, authenticated_user=authenticated_user)
