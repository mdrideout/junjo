"""Session-authenticated management routes for evaluation-control tokens."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Path, Query, Response, status

from app.db_sqlite.evaluation_tokens.schemas import (
    DEFAULT_EVALUATION_TOKEN_PAGE_SIZE,
    MAX_EVALUATION_TOKEN_PAGE_SIZE,
    EvaluationTokenCreate,
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
    response_model=EvaluationTokenRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_evaluation_token",
)
async def create_evaluation_token(
    request: Annotated[EvaluationTokenCreate, Body()],
    authenticated_user: CurrentUser,
) -> EvaluationTokenRead:
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


@router.delete(
    "/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_evaluation_token",
    responses={404: {"description": "Access token not found"}},
)
async def delete_evaluation_token(
    token_id: Annotated[TokenId, Path()],
    authenticated_user: CurrentUser,
) -> Response:
    deleted = await service.delete_token(token_id, authenticated_user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Access token not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
