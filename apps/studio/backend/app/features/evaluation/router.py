"""Authenticated HTTP routes for Studio evaluation control and queries."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Body, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from app.features.evaluation import service
from app.features.evaluation.contract import (
    EvaluationConflictError,
    EvaluationCursorError,
    EvaluationNotFoundError,
)
from app.features.evaluation.schemas import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MAX_VERSION,
    CursorText,
    EvaluationAttemptDetail,
    EvaluationAttemptRead,
    EvaluationAttemptResult,
    EvaluationCaseCreate,
    EvaluationCaseRead,
    EvaluationConflictResponse,
    EvaluationDatasetCreate,
    EvaluationDatasetDetail,
    EvaluationDatasetList,
    EvaluationDatasetRead,
    EvaluationEvidenceBind,
    EvaluationEvidenceMembershipList,
    EvaluationRunDetail,
    EvaluationRunList,
    EvaluationRunScope,
    EvaluationRunStart,
    ExecutableType,
    ExecutionIdentityText,
    KeyText,
    NameText,
    OpenTelemetrySpanReference,
    RecordId,
    SemanticExecutionReference,
    ServiceNamespaceText,
    TargetKind,
)
from app.features.evaluation_tokens.dependencies import (
    EvaluationReadAccess,
    EvaluationWriteAccess,
)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


def _conflict(error: EvaluationConflictError) -> JSONResponse:
    body = EvaluationConflictResponse(code=error.code, message=str(error))
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


def _not_found(error: EvaluationNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(error)})


def _invalid_cursor() -> HTTPException:
    return HTTPException(
        status_code=422,
        detail="Invalid pagination cursor",
    )


@router.post(
    "/datasets",
    response_model=EvaluationDatasetRead,
    operation_id="create_evaluation_dataset",
    responses={409: {"model": EvaluationConflictResponse}},
)
async def create_dataset(
    request: Annotated[EvaluationDatasetCreate, Body()],
    authenticated_user: EvaluationWriteAccess,
) -> EvaluationDatasetRead | JSONResponse:
    try:
        return await service.create_dataset(request, authenticated_user)
    except EvaluationConflictError as error:
        return _conflict(error)


@router.get(
    "/datasets",
    response_model=EvaluationDatasetList,
    operation_id="list_evaluation_datasets",
)
async def list_datasets(
    _authenticated_user: EvaluationReadAccess,
    application_key: Annotated[KeyText | None, Query()] = None,
    cursor: Annotated[CursorText | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> EvaluationDatasetList:
    try:
        return await service.list_datasets(
            application_key=application_key,
            cursor=cursor,
            limit=limit,
        )
    except EvaluationCursorError:
        raise _invalid_cursor() from None


@router.get(
    "/datasets/{dataset_id}",
    response_model=EvaluationDatasetDetail,
    operation_id="get_evaluation_dataset",
    responses={404: {"description": "Dataset not found"}},
)
async def get_dataset(
    dataset_id: Annotated[RecordId, Path()],
    _authenticated_user: EvaluationReadAccess,
) -> EvaluationDatasetDetail | JSONResponse:
    try:
        return await service.get_dataset(dataset_id)
    except EvaluationNotFoundError as error:
        return _not_found(error)


@router.post(
    "/datasets/{dataset_id}/cases",
    response_model=EvaluationCaseRead,
    operation_id="add_evaluation_case",
    responses={
        404: {"description": "Dataset not found"},
        409: {"model": EvaluationConflictResponse},
    },
)
async def add_case(
    dataset_id: Annotated[RecordId, Path()],
    request: Annotated[EvaluationCaseCreate, Body()],
    authenticated_user: EvaluationWriteAccess,
) -> EvaluationCaseRead | JSONResponse:
    try:
        return await service.add_case(
            dataset_id=dataset_id,
            request=request,
            authenticated_user=authenticated_user,
        )
    except EvaluationNotFoundError as error:
        return _not_found(error)
    except EvaluationConflictError as error:
        return _conflict(error)


@router.put(
    "/datasets/{dataset_id}/lock",
    response_model=EvaluationDatasetRead,
    operation_id="lock_evaluation_dataset",
    responses={404: {"description": "Dataset not found"}},
)
async def lock_dataset(
    dataset_id: Annotated[RecordId, Path()],
    authenticated_user: EvaluationWriteAccess,
) -> EvaluationDatasetRead | JSONResponse:
    try:
        return await service.lock_dataset(dataset_id, authenticated_user)
    except EvaluationNotFoundError as error:
        return _not_found(error)


@router.post(
    "/runs",
    response_model=EvaluationRunDetail,
    operation_id="start_evaluation_run",
    responses={
        404: {"description": "Dataset not found"},
        409: {"model": EvaluationConflictResponse},
    },
)
async def start_run(
    request: Annotated[EvaluationRunStart, Body()],
    authenticated_user: EvaluationWriteAccess,
) -> EvaluationRunDetail | JSONResponse:
    try:
        return await service.start_run(request, authenticated_user)
    except EvaluationNotFoundError as error:
        return _not_found(error)
    except EvaluationConflictError as error:
        return _conflict(error)


@router.get(
    "/runs",
    response_model=EvaluationRunList,
    operation_id="list_evaluation_runs",
)
async def list_runs(
    _authenticated_user: EvaluationReadAccess,
    dataset_id: Annotated[RecordId | None, Query()] = None,
    target_kind: Annotated[TargetKind | None, Query()] = None,
    target_key: Annotated[KeyText | None, Query()] = None,
    input_version: Annotated[int | None, Query(ge=1, le=MAX_VERSION)] = None,
    evaluation_name: Annotated[NameText | None, Query()] = None,
    cursor: Annotated[CursorText | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> EvaluationRunList:
    try:
        return await service.list_runs(
            scope=EvaluationRunScope(
                dataset_id=dataset_id,
                target_kind=target_kind,
                target_key=target_key,
                input_version=input_version,
                evaluation_name=evaluation_name,
            ),
            cursor=cursor,
            limit=limit,
        )
    except EvaluationCursorError:
        raise _invalid_cursor() from None


@router.get(
    "/runs/{run_id}",
    response_model=EvaluationRunDetail,
    operation_id="get_evaluation_run",
    responses={404: {"description": "Run not found"}},
)
async def get_run(
    run_id: Annotated[RecordId, Path()],
    _authenticated_user: EvaluationReadAccess,
) -> EvaluationRunDetail | JSONResponse:
    try:
        return await service.get_run(run_id)
    except EvaluationNotFoundError as error:
        return _not_found(error)


@router.get(
    "/attempts/{attempt_id}",
    response_model=EvaluationAttemptDetail,
    operation_id="get_evaluation_attempt",
    responses={404: {"description": "Attempt not found"}},
)
async def get_attempt(
    attempt_id: Annotated[RecordId, Path()],
    _authenticated_user: EvaluationReadAccess,
) -> EvaluationAttemptDetail | JSONResponse:
    try:
        return await service.get_attempt(attempt_id)
    except EvaluationNotFoundError as error:
        return _not_found(error)


@router.put(
    "/attempts/{attempt_id}/evidence",
    response_model=EvaluationAttemptRead,
    operation_id="bind_evaluation_attempt_evidence",
    responses={
        404: {"description": "Attempt not found"},
        409: {"model": EvaluationConflictResponse},
    },
)
async def bind_attempt_evidence(
    attempt_id: Annotated[RecordId, Path()],
    request: Annotated[EvaluationEvidenceBind, Body()],
    authenticated_user: EvaluationWriteAccess,
) -> EvaluationAttemptRead | JSONResponse:
    try:
        return await service.bind_attempt_evidence(
            attempt_id=attempt_id,
            evidence=request.evidence,
            authenticated_user=authenticated_user,
        )
    except EvaluationNotFoundError as error:
        return _not_found(error)
    except EvaluationConflictError as error:
        return _conflict(error)


@router.put(
    "/attempts/{attempt_id}/result",
    response_model=EvaluationAttemptRead,
    operation_id="record_evaluation_attempt_result",
    responses={
        404: {"description": "Attempt not found"},
        409: {"model": EvaluationConflictResponse},
    },
)
async def record_attempt_result(
    attempt_id: Annotated[RecordId, Path()],
    request: Annotated[EvaluationAttemptResult, Body()],
    authenticated_user: EvaluationWriteAccess,
) -> EvaluationAttemptRead | JSONResponse:
    try:
        return await service.record_attempt_result(
            attempt_id=attempt_id,
            result=request,
            authenticated_user=authenticated_user,
        )
    except EvaluationNotFoundError as error:
        return _not_found(error)
    except EvaluationConflictError as error:
        return _conflict(error)


@router.get(
    "/evidence-membership",
    response_model=EvaluationEvidenceMembershipList,
    operation_id="find_evaluation_evidence_membership",
)
async def find_evidence_membership(
    _authenticated_user: EvaluationReadAccess,
    evidence_kind: Annotated[
        Literal["junjo_execution", "otel_span"],
        Query(alias="kind"),
    ],
    service_namespace: Annotated[ServiceNamespaceText, Query()],
    service_name: Annotated[ExecutionIdentityText, Query()],
    executable_type: Annotated[ExecutableType | None, Query()] = None,
    runtime_id: Annotated[ExecutionIdentityText | None, Query()] = None,
    trace_id: Annotated[str | None, Query(pattern=r"^[0-9a-f]{32}$")] = None,
    span_id: Annotated[str | None, Query(pattern=r"^[0-9a-f]{16}$")] = None,
    cursor: Annotated[CursorText | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> EvaluationEvidenceMembershipList:
    if evidence_kind == "junjo_execution":
        if (
            executable_type is None
            or runtime_id is None
            or trace_id is not None
            or span_id is not None
        ):
            raise HTTPException(status_code=422, detail="Invalid junjo_execution evidence identity")
        evidence = SemanticExecutionReference(
            service_namespace=service_namespace,
            service_name=service_name,
            executable_type=executable_type,
            runtime_id=runtime_id,
        )
    else:
        if (
            trace_id is None
            or span_id is None
            or executable_type is not None
            or runtime_id is not None
        ):
            raise HTTPException(status_code=422, detail="Invalid otel_span evidence identity")
        evidence = OpenTelemetrySpanReference(
            service_namespace=service_namespace,
            service_name=service_name,
            trace_id=trace_id,
            span_id=span_id,
        )
    try:
        return await service.find_evidence_membership(
            evidence=evidence,
            cursor=cursor,
            limit=limit,
        )
    except EvaluationCursorError:
        raise _invalid_cursor() from None
