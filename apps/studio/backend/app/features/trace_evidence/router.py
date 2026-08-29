"""Authenticated HTTP boundary for cohesive trace evidence."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Path
from fastapi.responses import JSONResponse

from app.features.evaluation.contract import EvaluationNotFoundError
from app.features.evaluation.schemas import RecordId
from app.features.evaluation_tokens.dependencies import EvidenceReadAccess
from app.features.execution_resolution.contract import ExecutionResolutionConflictError
from app.features.execution_resolution.schemas import ExecutionResolutionConflictResponse
from app.features.trace_evidence import service
from app.features.trace_evidence.schemas import (
    AttemptEvidenceManifest,
    SelectedSpanEvidenceResponse,
    SelectedSpanRequest,
    TraceEvidence,
)

router = APIRouter(prefix="/trace-evidence", tags=["trace-evidence"])


@router.get(
    "/{trace_id}",
    response_model=TraceEvidence,
    operation_id="get_trace_evidence",
    responses={404: {"description": "Trace not found"}},
)
async def get_trace_evidence(
    trace_id: Annotated[str, Path(pattern="^[0-9a-f]{32}$")],
    _authenticated_user: EvidenceReadAccess,
) -> TraceEvidence | JSONResponse:
    """Get complete raw evidence and verified annotations for one trace."""
    evidence = await service.get_trace_evidence(trace_id)
    if evidence is None:
        return JSONResponse(status_code=404, content={"detail": "Trace not found"})
    return evidence


def _resolution_conflict(error: ExecutionResolutionConflictError) -> JSONResponse:
    body = ExecutionResolutionConflictResponse(
        code="ambiguous_execution_identity",
        message=str(error),
        match_count=error.match_count,
    )
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


@router.get(
    "/attempts/{attempt_id}/manifest",
    response_model=AttemptEvidenceManifest,
    operation_id="get_attempt_evidence_manifest",
    responses={
        404: {"description": "Attempt or bound evidence not found"},
        409: {"model": ExecutionResolutionConflictResponse},
    },
)
async def get_attempt_evidence_manifest(
    attempt_id: Annotated[RecordId, Path()],
    _authenticated_user: EvidenceReadAccess,
) -> AttemptEvidenceManifest | JSONResponse:
    """Get a payload-light trace manifest for one evaluation Attempt."""
    try:
        manifest = await service.get_attempt_evidence_manifest(attempt_id)
    except EvaluationNotFoundError:
        manifest = None
    except ExecutionResolutionConflictError as error:
        return _resolution_conflict(error)
    if manifest is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Attempt evidence not found"},
        )
    return manifest


@router.post(
    "/attempts/{attempt_id}/spans",
    response_model=SelectedSpanEvidenceResponse,
    operation_id="get_attempt_span_evidence",
    responses={
        404: {"description": "Attempt or bound evidence not found"},
        409: {"model": ExecutionResolutionConflictResponse},
    },
)
async def get_attempt_span_evidence(
    attempt_id: Annotated[RecordId, Path()],
    request: Annotated[SelectedSpanRequest, Body()],
    _authenticated_user: EvidenceReadAccess,
) -> SelectedSpanEvidenceResponse | JSONResponse:
    """Get complete evidence for exact span IDs in an Attempt's bound trace."""
    try:
        evidence = await service.get_attempt_span_evidence(
            attempt_id=attempt_id,
            span_ids=request.span_ids,
        )
    except EvaluationNotFoundError:
        evidence = None
    except ExecutionResolutionConflictError as error:
        return _resolution_conflict(error)
    if evidence is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Attempt evidence not found"},
        )
    return evidence
