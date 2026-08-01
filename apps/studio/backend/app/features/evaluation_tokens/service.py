"""Business logic for separately scoped evaluation-control tokens."""

from __future__ import annotations

import secrets
from datetime import datetime

from app.common.audit import AuditAction, AuditResource, audit_log
from app.common.datetime_utils import utcnow
from app.db_sqlite.evaluation_tokens.repository import EvaluationTokenRepository
from app.db_sqlite.evaluation_tokens.schemas import (
    EvaluationTokenCreate,
    EvaluationTokenList,
    EvaluationTokenRead,
    EvaluationTokenScope,
)
from app.features.auth.models import AuthenticatedUser
from app.features.evaluation_tokens.contract import (
    EvaluationTokenAuthenticationError,
    EvaluationTokenAuthorizationError,
)

TOKEN_PREFIX = "jcli_"
TOKEN_SECRET_BYTES = 48


def _generate_token() -> str:
    """Generate one opaque, canonical developer access token."""
    return TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_SECRET_BYTES)


async def create_token(
    request: EvaluationTokenCreate,
    authenticated_user: AuthenticatedUser,
) -> EvaluationTokenRead:
    if request.expires_at is not None and request.expires_at <= utcnow():
        raise ValueError("expires_at must be in the future")
    token = _generate_token()
    scopes = frozenset(request.scopes)
    audit_log(
        AuditAction.CREATE,
        AuditResource.EVALUATION_TOKEN,
        None,
        authenticated_user,
        {
            "name": request.name,
            "token_preview": token[:12] + "...",
            "scopes": [scope.value for scope in request.scopes],
        },
    )
    created = await EvaluationTokenRepository.create(
        name=request.name,
        token=token,
        scopes=scopes,
        expires_at=request.expires_at,
        created_by_user_id=authenticated_user.user_id,
    )
    return created


async def list_tokens(
    *,
    cursor: str | None,
    limit: int,
    authenticated_user: AuthenticatedUser,
) -> EvaluationTokenList:
    audit_log(
        AuditAction.LIST,
        AuditResource.EVALUATION_TOKEN,
        None,
        authenticated_user,
    )
    return await EvaluationTokenRepository.list_tokens(cursor=cursor, limit=limit)


async def delete_token(
    token_id: str,
    authenticated_user: AuthenticatedUser,
) -> bool:
    audit_log(
        AuditAction.DELETE,
        AuditResource.EVALUATION_TOKEN,
        token_id,
        authenticated_user,
    )
    return await EvaluationTokenRepository.delete(token_id)


async def authenticate_token(
    token: str,
    required_scopes: frozenset[EvaluationTokenScope],
    *,
    authenticated_at: datetime | None = None,
) -> AuthenticatedUser:
    """Authenticate one bearer token with a read-only database operation."""
    record = await EvaluationTokenRepository.get_for_authentication(token)
    if record is None:
        raise EvaluationTokenAuthenticationError

    now = authenticated_at or utcnow()
    if (record.expires_at is not None and record.expires_at <= now) or not record.user_is_active:
        raise EvaluationTokenAuthenticationError

    missing = required_scopes - record.scopes
    if missing:
        raise EvaluationTokenAuthorizationError(frozenset(scope.value for scope in missing))

    return AuthenticatedUser(
        email=record.user_email,
        user_id=record.user_id,
        authenticated_at=now,
        session_id=f"evaluation-token:{record.id}",
    )
