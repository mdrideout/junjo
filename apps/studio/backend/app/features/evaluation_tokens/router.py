"""Session-authenticated management routes for evaluation-control tokens."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse

from app.db_sqlite.evaluation_tokens.schemas import (
    DEFAULT_EVALUATION_TOKEN_PAGE_SIZE,
    MAX_EVALUATION_TOKEN_PAGE_SIZE,
    EvaluationTokenCreate,
    EvaluationTokenCreated,
    EvaluationTokenList,
    EvaluationTokenRead,
    TokenCursor,
    TokenId,
)
from app.features.auth.dependencies import CurrentUser
from app.features.evaluation_tokens import service
from app.features.evaluation_tokens.contract import EvaluationTokenCursorError

router = APIRouter(prefix="/evaluation-tokens", tags=["evaluation-tokens"])


@router.post(
    "",
    response_model=EvaluationTokenCreated,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_evaluation_token",
)
async def create_evaluation_token(
    request: Annotated[EvaluationTokenCreate, Body()],
    authenticated_user: CurrentUser,
) -> EvaluationTokenCreated:
    try:
        return await service.create_token(request, authenticated_user)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@router.get(
    "",
    response_model=EvaluationTokenList,
    operation_id="list_evaluation_tokens",
)
async def list_evaluation_tokens(
    authenticated_user: CurrentUser,
    cursor: Annotated[TokenCursor | None, Query()] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_EVALUATION_TOKEN_PAGE_SIZE),
    ] = DEFAULT_EVALUATION_TOKEN_PAGE_SIZE,
) -> EvaluationTokenList:
    try:
        return await service.list_tokens(
            cursor=cursor,
            limit=limit,
            authenticated_user=authenticated_user,
        )
    except EvaluationTokenCursorError:
        raise HTTPException(status_code=422, detail="Invalid pagination cursor") from None


@router.put(
    "/{token_id}/revoke",
    response_model=EvaluationTokenRead,
    operation_id="revoke_evaluation_token",
    responses={404: {"description": "Evaluation token not found"}},
)
async def revoke_evaluation_token(
    token_id: Annotated[TokenId, Path()],
    authenticated_user: CurrentUser,
) -> EvaluationTokenRead | JSONResponse:
    revoked = await service.revoke_token(token_id, authenticated_user)
    if revoked is None:
        return JSONResponse(status_code=404, content={"detail": "Evaluation token not found"})
    return revoked
