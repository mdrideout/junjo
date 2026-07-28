"""Authenticated HTTP routes for Studio evaluation control and queries."""

from __future__ import annotations

from typing import Annotated

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
    EvaluationExecutionBind,
    EvaluationExecutionMembershipList,
    EvaluationRunDetail,
    EvaluationRunList,
    EvaluationRunStart,
    ExecutableType,
    ExecutionIdentityText,
    KeyText,
    RecordId,
    SemanticExecutionReference,
    ServiceNamespaceText,
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
    application_key: Annotated[KeyText, Query()],
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
    cursor: Annotated[CursorText | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> EvaluationRunList:
    try:
        return await service.list_runs(
            dataset_id=dataset_id,
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
    "/attempts/{attempt_id}/execution",
    response_model=EvaluationAttemptRead,
    operation_id="bind_evaluation_attempt_execution",
    responses={
        404: {"description": "Attempt not found"},
        409: {"model": EvaluationConflictResponse},
    },
)
async def bind_attempt_execution(
    attempt_id: Annotated[RecordId, Path()],
    request: Annotated[EvaluationExecutionBind, Body()],
    authenticated_user: EvaluationWriteAccess,
) -> EvaluationAttemptRead | JSONResponse:
    try:
        return await service.bind_attempt_execution(
            attempt_id=attempt_id,
            execution=request.execution,
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
    "/execution-membership",
    response_model=EvaluationExecutionMembershipList,
    operation_id="find_evaluation_execution_membership",
)
async def find_execution_membership(
    _authenticated_user: EvaluationReadAccess,
    service_namespace: Annotated[ServiceNamespaceText, Query()],
    service_name: Annotated[ExecutionIdentityText, Query()],
    executable_type: Annotated[ExecutableType, Query()],
    runtime_id: Annotated[ExecutionIdentityText, Query()],
    cursor: Annotated[CursorText | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> EvaluationExecutionMembershipList:
    try:
        return await service.find_execution_membership(
            execution=SemanticExecutionReference(
                service_namespace=service_namespace,
                service_name=service_name,
                executable_type=executable_type,
                runtime_id=runtime_id,
            ),
            cursor=cursor,
            limit=limit,
        )
    except EvaluationCursorError:
        raise _invalid_cursor() from None
