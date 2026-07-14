"""Typed HTTP route for Workflow Store diagnostics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse

from app.features.auth.dependencies import CurrentUser
from app.features.workflow_diagnostics import service
from app.features.workflow_diagnostics.assembler import WorkflowEvidenceError
from app.features.workflow_diagnostics.schemas import (
    WorkflowEvidenceErrorResponse,
    WorkflowStoreDiagnostic,
)

router = APIRouter(prefix="/workflow-executions", tags=["workflow-executions"])


def _semantic_error(error: WorkflowEvidenceError) -> JSONResponse:
    body = WorkflowEvidenceErrorResponse(
        code=error.code,
        message=error.message,
        diagnostics=error.diagnostics,
    )
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


@router.get(
    "/{trace_id}/{workflow_span_id}/store",
    response_model=WorkflowStoreDiagnostic,
    operation_id="get_workflow_store_diagnostic",
    responses={
        404: {"description": "Workflow execution not found"},
        409: {"model": WorkflowEvidenceErrorResponse},
    },
)
async def get_workflow_store_diagnostic(
    trace_id: Annotated[str, Path(pattern="^[0-9a-f]{32}$")],
    workflow_span_id: Annotated[str, Path(pattern="^[0-9a-f]{16}$")],
    _authenticated_user: CurrentUser,
) -> WorkflowStoreDiagnostic | JSONResponse:
    """Get backend-authoritative Store reconstruction for one Workflow owner."""
    try:
        detail = await service.get_workflow_store(trace_id, workflow_span_id)
    except WorkflowEvidenceError as error:
        return _semantic_error(error)
    if detail is None:
        return JSONResponse(status_code=404, content={"detail": "Workflow execution not found"})
    return detail
