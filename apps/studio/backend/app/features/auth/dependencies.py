"""
FastAPI dependencies for authentication.

Provides dependency injection for auth-protected endpoints.
Returns AuthenticatedUser objects with full audit context.
"""

from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.db_sqlite.users.repository import UserRepository
from app.features.auth.models import AuthenticatedUser


async def get_authenticated_user(request: Request) -> AuthenticatedUser:
    """
    Dependency to get authenticated user with full audit context from session.

    Session is automatically decrypted and validated by middleware stack:
    1. SecureCookiesMiddleware decrypts the cookie
    2. SessionMiddleware validates signature and populates request.session

    This dependency:
    - Reads userEmail from request.session
    - Queries database to get full user details (including user_id)
    - Extracts session metadata for audit logging
    - Returns AuthenticatedUser object with complete context
    - Raises 401 if session is invalid, missing, or user not found

    Args:
        request: FastAPI request object (with session populated by middleware)

    Returns:
        AuthenticatedUser object with email, user_id, authenticated_at, session_id

    Raises:
        HTTPException: 401 if session is invalid, missing, or user not found

    Example:
        ```python
        from app.features.auth.dependencies import CurrentUser

        @router.get("/protected")
        async def protected_endpoint(authenticated_user: CurrentUser):
            # authenticated_user.email, authenticated_user.user_id, etc.
            return {"user": authenticated_user.email}
        ```
    """
    # Check if session exists and has user email
    user_email = request.session.get("userEmail")

    if user_email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: No valid session",
        )

    # Query database to get full user details
    user = await UserRepository.get_by_email(user_email)

    if user is None:
        # User was deleted after session was created
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: User not found",
        )

    # Extract session metadata for audit logging
    session_id = request.session.get("session_id", "unknown")

    # Parse authenticated_at timestamp from session (ISO format)
    authenticated_at_str = request.session.get("authenticated_at")
    if authenticated_at_str:
        try:
            authenticated_at = datetime.fromisoformat(authenticated_at_str)
        except (ValueError, TypeError):
            # Fallback if timestamp is malformed
            authenticated_at = datetime.now()
    else:
        # Fallback if timestamp not in session (older sessions)
        authenticated_at = datetime.now()

    # Create and return AuthenticatedUser object
    return AuthenticatedUser(
        email=user.email,
        user_id=user.id,
        authenticated_at=authenticated_at,
        session_id=session_id,
    )


# Type alias for dependency injection
# Use this in route signatures: authenticated_user: CurrentUser
CurrentUser = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]
