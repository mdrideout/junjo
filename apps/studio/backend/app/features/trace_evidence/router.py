"""Authenticated HTTP boundary for cohesive trace evidence."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse

from app.features.auth.dependencies import CurrentUser
from app.features.trace_evidence import service
from app.features.trace_evidence.schemas import TraceEvidence

router = APIRouter(prefix="/trace-evidence", tags=["trace-evidence"])


@router.get(
    "/{trace_id}",
    response_model=TraceEvidence,
    operation_id="get_trace_evidence",
    responses={404: {"description": "Trace not found"}},
)
async def get_trace_evidence(
    trace_id: Annotated[str, Path(pattern="^[0-9a-f]{32}$")],
    _authenticated_user: CurrentUser,
) -> TraceEvidence | JSONResponse:
    """Get complete raw evidence and verified annotations for one trace."""
    evidence = await service.get_trace_evidence(trace_id)
    if evidence is None:
        return JSONResponse(status_code=404, content={"detail": "Trace not found"})
    return evidence
