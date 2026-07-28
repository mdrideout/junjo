"""Business logic for separately scoped evaluation-control tokens."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime

from app.common.audit import AuditAction, AuditResource, audit_log
from app.common.datetime_utils import utcnow
from app.db_sqlite.evaluation_tokens.repository import EvaluationTokenRepository
from app.db_sqlite.evaluation_tokens.schemas import (
    EvaluationTokenCreate,
    EvaluationTokenCreated,
    EvaluationTokenList,
    EvaluationTokenRead,
    EvaluationTokenScope,
)
from app.features.auth.models import AuthenticatedUser
from app.features.evaluation_tokens.contract import (
    EvaluationTokenAuthenticationError,
    EvaluationTokenAuthorizationError,
)

_TOKEN_PATTERN = re.compile(r"^(?P<prefix>junjo_eval_[A-Za-z0-9_-]{12})\.[A-Za-z0-9_-]{43}$")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _generate_token() -> tuple[str, str]:
    prefix = f"junjo_eval_{secrets.token_urlsafe(9)}"
    token = f"{prefix}.{secrets.token_urlsafe(32)}"
    return prefix, token


async def create_token(
    request: EvaluationTokenCreate,
    authenticated_user: AuthenticatedUser,
) -> EvaluationTokenCreated:
    if request.expires_at is not None and request.expires_at <= utcnow():
        raise ValueError("expires_at must be in the future")
    prefix, token = _generate_token()
    scopes = frozenset(request.scopes)
    audit_log(
        AuditAction.CREATE,
        AuditResource.EVALUATION_TOKEN,
        None,
        authenticated_user,
        {
            "name": request.name,
            "prefix": prefix,
            "scopes": [scope.value for scope in request.scopes],
        },
    )
    created = await EvaluationTokenRepository.create(
        name=request.name,
        prefix=prefix,
        secret_hash=_hash_token(token),
        scopes=scopes,
        expires_at=request.expires_at,
        created_by_user_id=authenticated_user.user_id,
    )
    return EvaluationTokenCreated(**created.model_dump(), token=token)


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


async def revoke_token(
    token_id: str,
    authenticated_user: AuthenticatedUser,
) -> EvaluationTokenRead | None:
    audit_log(
        AuditAction.UPDATE,
        AuditResource.EVALUATION_TOKEN,
        token_id,
        authenticated_user,
    )
    return await EvaluationTokenRepository.revoke(token_id)


async def authenticate_token(
    token: str,
    required_scopes: frozenset[EvaluationTokenScope],
    *,
    authenticated_at: datetime | None = None,
) -> AuthenticatedUser:
    """Authenticate one bearer token with a read-only database operation."""
    matched = _TOKEN_PATTERN.fullmatch(token)
    if matched is None:
        raise EvaluationTokenAuthenticationError
    record = await EvaluationTokenRepository.get_for_authentication(matched.group("prefix"))
    if record is None or not secrets.compare_digest(record.secret_hash, _hash_token(token)):
        raise EvaluationTokenAuthenticationError

    now = authenticated_at or utcnow()
    if (
        record.revoked_at is not None
        or (record.expires_at is not None and record.expires_at <= now)
        or not record.user_is_active
    ):
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
