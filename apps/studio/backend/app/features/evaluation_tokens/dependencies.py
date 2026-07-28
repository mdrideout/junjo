"""Session-or-bearer authorization dependencies for evaluation APIs."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db_sqlite.evaluation_tokens.schemas import EvaluationTokenScope
from app.features.auth.dependencies import get_authenticated_user
from app.features.auth.models import AuthenticatedUser
from app.features.evaluation_tokens.contract import (
    EvaluationTokenAuthenticationError,
    EvaluationTokenAuthorizationError,
)
from app.features.evaluation_tokens.service import authenticate_token

_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="EvaluationControlToken",
    description=(
        "A separately scoped Studio evaluation-control token. "
        "Studio ingestion API keys are not accepted."
    ),
)

AccessDependency = Callable[..., Coroutine[Any, Any, AuthenticatedUser]]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_scopes(
    *required_scopes: EvaluationTokenScope,
) -> AccessDependency:
    required = frozenset(required_scopes)

    async def get_scoped_access(
        request: Request,
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Security(_bearer),
        ] = None,
    ) -> AuthenticatedUser:
        authorization_header = request.headers.get("authorization")
        if credentials is not None:
            if credentials.scheme.lower() != "bearer":
                raise _unauthorized("Unsupported authorization scheme")
            try:
                return await authenticate_token(credentials.credentials, required)
            except EvaluationTokenAuthenticationError:
                raise _unauthorized("Invalid or expired evaluation token") from None
            except EvaluationTokenAuthorizationError as error:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "insufficient_evaluation_token_scope",
                        "missing_scopes": sorted(error.missing_scopes),
                    },
                ) from None

        if authorization_header is not None:
            raise _unauthorized("Invalid evaluation token authorization header")
        return await get_authenticated_user(request)

    return get_scoped_access


get_evaluation_read_access = require_scopes(EvaluationTokenScope.EVALUATION_READ)
get_evaluation_write_access = require_scopes(EvaluationTokenScope.EVALUATION_WRITE)
get_evidence_read_access = require_scopes(EvaluationTokenScope.EVIDENCE_READ)

EvaluationReadAccess = Annotated[
    AuthenticatedUser,
    Depends(get_evaluation_read_access),
]
EvaluationWriteAccess = Annotated[
    AuthenticatedUser,
    Depends(get_evaluation_write_access),
]
EvidenceReadAccess = Annotated[
    AuthenticatedUser,
    Depends(get_evidence_read_access),
]
