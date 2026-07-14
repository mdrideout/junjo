"""Authenticated HTTP boundary for exact execution resolution."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.features.auth.dependencies import CurrentUser
from app.features.execution_resolution import service
from app.features.execution_resolution.contract import ExecutionResolutionConflictError
from app.features.execution_resolution.schemas import (
    ExecutionResolution,
    ExecutionResolutionConflictResponse,
    ExecutionResolutionQuery,
)

router = APIRouter(prefix="/execution-resolution", tags=["execution-resolution"])


@router.get(
    "",
    response_model=ExecutionResolution,
    operation_id="resolve_execution",
    responses={
        404: {"description": "Execution owner span not found"},
        409: {"model": ExecutionResolutionConflictResponse},
    },
)
async def resolve_execution(
    _authenticated_user: CurrentUser,
    query: Annotated[ExecutionResolutionQuery, Query()],
) -> ExecutionResolution | JSONResponse:
    try:
        resolved = await service.resolve_execution(
            service_namespace=query.service_namespace,
            service_name=query.service_name,
            executable_type=query.executable_type,
            runtime_id=query.runtime_id,
        )
    except ExecutionResolutionConflictError as error:
        body = ExecutionResolutionConflictResponse(
            code="ambiguous_execution_identity",
            message=str(error),
            match_count=error.match_count,
        )
        return JSONResponse(status_code=409, content=body.model_dump(mode="json"))
    if resolved is None:
        return JSONResponse(status_code=404, content={"detail": "Execution not found"})
    return resolved
