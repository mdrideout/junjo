"""Typed HTTP routes for Agent execution diagnostics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.features.agent_diagnostics import service
from app.features.agent_diagnostics.contract import AgentEvidenceError
from app.features.agent_diagnostics.schemas import (
    AgentEvidenceErrorResponse,
    AgentExecutionListQuery,
    AgentExecutionSummary,
)
from app.features.auth.dependencies import CurrentUser

router = APIRouter(prefix="/agent-executions", tags=["agent-executions"])


def _semantic_error(error: AgentEvidenceError) -> JSONResponse:
    body = AgentEvidenceErrorResponse(
        code=error.code,
        message=error.message,
        diagnostics=error.diagnostics,
    )
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


@router.get(
    "",
    response_model=list[AgentExecutionSummary],
    operation_id="list_agent_executions",
    responses={
        409: {"model": AgentEvidenceErrorResponse},
    },
)
async def list_agent_executions(
    _authenticated_user: CurrentUser,
    query: Annotated[AgentExecutionListQuery, Query()],
) -> list[AgentExecutionSummary] | JSONResponse:
    """List strict active-contract Agent executions in one service scope."""
    try:
        return await service.list_agent_executions(
            service_namespace=query.service_namespace,
            service_name=query.service_name,
            agent_key=query.agent_key,
            structural_id=query.structural_id,
            service_version=query.service_version,
            outcome=query.outcome,
            start_time=query.start_time,
            end_time=query.end_time,
            limit=query.limit,
        )
    except AgentEvidenceError as error:
        return _semantic_error(error)
