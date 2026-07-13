"""Authentication models for user context and audit logging.

This module defines the AuthenticatedUser dataclass which represents
an authenticated user with complete audit context. This object flows
through router → service → repository layers to enable comprehensive
audit logging while maintaining clean separation of concerns.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AuthenticatedUser:
    """Represents an authenticated user with full audit context.

    This immutable object is passed through all application layers
    (router → service → repository) to enable defense-in-depth via
    comprehensive audit logging.

    The frozen=True makes this immutable, preventing accidental modification
    during request processing and ensuring audit trail integrity.

    Attributes:
        email: User's email address (primary identifier)
        user_id: User's database ID (for efficient lookups)
        authenticated_at: Timestamp when this session was created
        session_id: Unique session identifier for audit correlation
            (allows tracking all actions in a single session)

    Example:
        >>> user = AuthenticatedUser(
        ...     email="admin@example.com",
        ...     user_id="usr_abc123",
        ...     authenticated_at=datetime.now(),
        ...     session_id="sess_xyz789"
        ... )
        >>> print(user)
        User(admin@example.com, session=sess_xyz7...)

    Usage in routers:
        ```python
        from app.features.auth.dependencies import CurrentUser

        @router.post("/api_keys")
        async def create_api_key(
            request: APIKeyCreate,
            authenticated_user: CurrentUser  # ← Dependency injection
        ):
            # authenticated_user is automatically populated by FastAPI
            return await APIKeyService.create_api_key(
                request.name,
                authenticated_user  # ← Pass to service layer
            )
        ```

    Usage in services:
        ```python
        @staticmethod
        async def create_api_key(
            name: str,
            authenticated_user: AuthenticatedUser
        ):
            # Audit log who is creating the key
            audit_log("create", "api_key", None, authenticated_user)

            # Pass user context to repository
            return await APIKeyRepository.create(
                name,
                authenticated_user  # ← Pass to repository layer
            )
        ```

    Usage in repositories:
        ```python
        @staticmethod
        async def create(
            name: str,
            authenticated_user: AuthenticatedUser
        ):
            # Data-layer audit logging (defense in depth)
            audit_log("db_insert", "api_key", None, authenticated_user)

            # Perform database operation
            db_obj = APIKeyTable(name=name)
            # ...
        ```
    """

    email: str
    user_id: str
    authenticated_at: datetime
    session_id: str

    def __str__(self) -> str:
        """String representation for logging.

        Returns:
            Human-readable string showing email and truncated session ID.
            Example: "User(admin@example.com, session=abc12345...)"
        """
        # Truncate session_id to first 8 chars for readability
        session_preview = self.session_id[:8] if len(self.session_id) >= 8 else self.session_id
        return f"User({self.email}, session={session_preview}...)"

    def __repr__(self) -> str:
        """Developer representation for debugging.

        Returns:
            Full dataclass representation with all fields.
        """
        return (
            f"AuthenticatedUser("
            f"email={self.email!r}, "
            f"user_id={self.user_id!r}, "
            f"authenticated_at={self.authenticated_at!r}, "
            f"session_id={self.session_id!r})"
        )


# System user for internal operations (migrations, background jobs, etc.)
# Used when no authenticated user context exists but audit logging is still required.
SYSTEM_USER = AuthenticatedUser(
    email="system@internal",
    user_id="system",
    authenticated_at=datetime.min,  # Epoch time indicates system operation
    session_id="system",
)
