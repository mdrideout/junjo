"""Audit logging utilities for defense-in-depth security.

This module provides structured audit logging functionality that captures
who performed which actions on what resources. Audit logs flow through all
application layers (router → service → repository) to create comprehensive
audit trails.

The audit logging pattern implements defense-in-depth by ensuring that
every layer logs actions with full authenticated user context, making it
possible to trace any action back to the specific user and session.
"""

from typing import Any

from loguru import logger

from app.features.auth.models import AuthenticatedUser


def audit_log(
    action: str,
    resource_type: str,
    resource_id: str | None,
    user: AuthenticatedUser,
    details: dict[str, Any] | None = None,
) -> None:
    """Log an auditable action with full user context.

    Creates a structured log entry that captures:
    - What action was performed (create, read, update, delete, etc.)
    - What type of resource was affected (api_key, user, etc.)
    - Which specific resource (ID)
    - Who performed the action (authenticated user)
    - When it was performed (timestamp from logger)
    - Additional context (optional details dict)

    These logs enable:
    - Security audits (who did what when)
    - Compliance reporting (data access trails)
    - Debugging (trace actions through system)
    - Incident response (identify malicious activity)

    Args:
        action: The action performed (lowercase).
            Common values: "create", "read", "update", "delete", "list"
            Data layer: "db_insert", "db_query", "db_update", "db_delete"
        resource_type: Type of resource affected (lowercase, singular).
            Examples: "api_key", "user", "llm_generation", "session"
        resource_id: Unique identifier of the affected resource.
            None for list operations or when ID not yet assigned.
        user: Authenticated user who performed the action.
            Provides email, user_id, session_id for full audit context.
        details: Optional dictionary with additional context.
            Examples: {"name": "Production Key"}, {"model": "gpt-4"}

    Example Router Layer:
        ```python
        @router.post("/api_keys")
        async def create_api_key(request: APIKeyCreate, user: CurrentUser):
            audit_log("create", "api_key", None, user, {"name": request.name})
            return await APIKeyService.create_api_key(request.name, user)
        ```

    Example Service Layer:
        ```python
        async def create_api_key(name: str, user: AuthenticatedUser):
            audit_log("create", "api_key", None, user, {"name": name})
            key_id = generate_id()
            return await APIKeyRepository.create(key_id, name, user)
        ```

    Example Repository Layer:
        ```python
        async def create(key_id: str, name: str, user: AuthenticatedUser):
            audit_log("db_insert", "api_key", key_id, user)
            db_obj = APIKeyTable(id=key_id, name=name)
            # ... database operations
        ```

    Log Output Format:
        ```
        2025-11-01 12:00:00 | INFO | AUDIT: CREATE api_key | user_email=admin@example.com
        user_id=usr_abc123 session_id=sess_xyz789 resource_id=key_456 action=create
        resource_type=api_key details={"name": "Production Key"}
        ```

    Notes:
        - All audit logs use INFO level (visible in production)
        - Logs are structured with extra fields for easy parsing/filtering
        - User context is immutable (frozen dataclass) to prevent tampering
        - Session ID allows correlating all actions in a single session
        - Details dict should not contain sensitive data (passwords, tokens)
    """
    # Format action and resource for consistent logging
    action_upper = action.upper()
    resource_display = f"{resource_type}"

    # Build log message
    message = f"AUDIT: {action_upper} {resource_display}"

    # Add resource ID to message if provided
    if resource_id:
        message += f" (id={resource_id})"

    # Create structured log entry with all context
    logger.info(
        message,
        extra={
            # Action context
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            # User context (who)
            "user_email": user.email,
            "user_id": user.user_id,
            "session_id": user.session_id,
            "authenticated_at": user.authenticated_at.isoformat(),
            # Additional context
            "details": details or {},
            # Audit marker for easy filtering
            "audit": True,
        },
    )


def audit_log_error(
    action: str,
    resource_type: str,
    resource_id: str | None,
    user: AuthenticatedUser,
    error: Exception,
    details: dict[str, Any] | None = None,
) -> None:
    """Log a failed auditable action.

    Similar to audit_log() but logs at ERROR level and includes exception details.
    Used when an action fails due to authorization, validation, or system errors.

    Args:
        action: The action that was attempted
        resource_type: Type of resource
        resource_id: Resource ID if known
        user: Authenticated user who attempted the action
        error: The exception that occurred
        details: Optional additional context

    Example:
        ```python
        try:
            await delete_api_key(key_id, user)
        except Exception as e:
            audit_log_error("delete", "api_key", key_id, user, e)
            raise
        ```
    """
    action_upper = action.upper()
    resource_display = f"{resource_type}"

    message = f"AUDIT ERROR: {action_upper} {resource_display} FAILED"

    if resource_id:
        message += f" (id={resource_id})"

    logger.error(
        message,
        extra={
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "user_email": user.email,
            "user_id": user.user_id,
            "session_id": user.session_id,
            "authenticated_at": user.authenticated_at.isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "details": details or {},
            "audit": True,
            "audit_error": True,
        },
    )


# Common audit actions (constants for consistency)
class AuditAction:
    """Standard audit action names for consistency."""

    # CRUD operations
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"

    # Database operations (repository layer)
    DB_INSERT = "db_insert"
    DB_QUERY = "db_query"
    DB_UPDATE = "db_update"
    DB_DELETE = "db_delete"

    # Authentication operations
    AUTH_LOGIN = "auth_login"
    AUTH_LOGOUT = "auth_logout"
    AUTH_FAILED = "auth_failed"

    # Authorization operations
    AUTHZ_CHECK = "authz_check"
    AUTHZ_DENIED = "authz_denied"


# Common resource types (constants for consistency)
class AuditResource:
    """Standard resource type names for consistency."""

    API_KEY = "api_key"
    USER = "user"
    SESSION = "session"
    LLM_GENERATION = "llm_generation"
    OTEL_SPAN = "otel_span"
    WORKFLOW = "workflow"
