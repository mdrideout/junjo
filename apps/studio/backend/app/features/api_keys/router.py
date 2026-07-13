"""
API Keys router.

Implements CRUD endpoints for API key management.
All endpoints require authentication for security (any authenticated user can CRUD).
"""

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from sqlalchemy.exc import IntegrityError

from app.common.audit import AuditAction, AuditResource, audit_log
from app.db_sqlite.api_keys.schemas import APIKeyCreate, APIKeyRead
from app.features.api_keys.service import APIKeyService
from app.features.auth.dependencies import CurrentUser

router = APIRouter(prefix="/api_keys", tags=["api_keys"])


@router.post("", response_model=APIKeyRead, status_code=status.HTTP_201_CREATED)
async def create_api_key(request: APIKeyCreate, authenticated_user: CurrentUser):
    """
    Create a new API key (requires authentication).

    Generates a unique 64-character alphanumeric key.
    Any authenticated user can create keys (shared resource).

    Args:
        request: APIKeyCreate with name
        authenticated_user: Authenticated user from session (injected by FastAPI)

    Returns:
        Created API key with id, key, name, created_at

    Raises:
        HTTPException: 401 if not authenticated, 500 if creation fails
    """
    # Audit log at router layer (defense in depth)
    audit_log(
        AuditAction.CREATE, AuditResource.API_KEY, None, authenticated_user, {"name": request.name}
    )

    logger.info(f"User {authenticated_user.email} creating API key: {request.name}")

    try:
        api_key = await APIKeyService.create_api_key(
            name=request.name, authenticated_user=authenticated_user
        )
        logger.info(f"Created API key: {api_key.id} by {authenticated_user.email}")
        return api_key
    except IntegrityError:
        # Extremely rare - key collision (nanoid is cryptographically random)
        logger.error("API key collision (should be impossible)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate unique API key",
        )
    except Exception as e:
        logger.error(f"Failed to create API key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create API key",
        )


@router.get("", response_model=list[APIKeyRead])
async def list_api_keys(authenticated_user: CurrentUser):
    """
    List all API keys, ordered by created_at descending (requires authentication).

    Any authenticated user can list keys (shared resource).

    Args:
        authenticated_user: Authenticated user from session (injected by FastAPI)

    Returns:
        List of all API keys (or empty list if none exist)

    Raises:
        HTTPException: 401 if not authenticated, 500 if listing fails
    """
    # Audit log at router layer (defense in depth)
    audit_log(AuditAction.LIST, AuditResource.API_KEY, None, authenticated_user)

    logger.info(f"User {authenticated_user.email} listing API keys")

    try:
        api_keys = await APIKeyService.list_api_keys(authenticated_user=authenticated_user)
        logger.info(f"Found {len(api_keys)} API keys for {authenticated_user.email}")
        return api_keys
    except Exception as e:
        logger.error(f"Failed to list API keys: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve API keys",
        )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(id: str, authenticated_user: CurrentUser):
    """
    Delete an API key by ID (requires authentication).

    Any authenticated user can delete keys (shared resource).

    Args:
        id: API key ID to delete
        authenticated_user: Authenticated user from session (injected by FastAPI)

    Returns:
        204 No Content if successful

    Raises:
        HTTPException: 401 if not authenticated, 404 if key not found, 500 if deletion fails
    """
    # Audit log at router layer (defense in depth)
    audit_log(AuditAction.DELETE, AuditResource.API_KEY, id, authenticated_user)

    logger.info(f"User {authenticated_user.email} deleting API key: {id}")

    try:
        deleted = await APIKeyService.delete_api_key(id, authenticated_user=authenticated_user)

        if not deleted:
            logger.warning(f"API key not found: {id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )

        logger.info(f"Deleted API key: {id} by {authenticated_user.email}")
        return None  # FastAPI returns 204 automatically

    except HTTPException:
        # Re-raise HTTPExceptions (like 404)
        raise
    except Exception as e:
        logger.error(f"Failed to delete API key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete API key",
        )
