"""Application service boundary for authenticated evaluation operations."""

from __future__ import annotations

from app.common.audit import audit_log
from app.features.auth.models import AuthenticatedUser
from app.features.evaluation.repository import EvaluationRepository
from app.features.evaluation.schemas import (
    EvaluationAttemptDetail,
    EvaluationAttemptRead,
    EvaluationAttemptResult,
    EvaluationCaseCreate,
    EvaluationCaseRead,
    EvaluationDatasetCreate,
    EvaluationDatasetDetail,
    EvaluationDatasetList,
    EvaluationDatasetRead,
    EvaluationExecutionMembershipList,
    EvaluationRunDetail,
    EvaluationRunList,
    EvaluationRunScope,
    EvaluationRunStart,
    SemanticExecutionReference,
)


async def create_dataset(
    request: EvaluationDatasetCreate,
    authenticated_user: AuthenticatedUser,
) -> EvaluationDatasetRead:
    audit_log(
        "create",
        "evaluation_dataset",
        None,
        authenticated_user,
        {"application_key": request.application_key, "key": request.key},
    )
    return await EvaluationRepository.create_dataset(request, authenticated_user)


async def list_datasets(
    *,
    application_key: str | None,
    cursor: str | None,
    limit: int,
) -> EvaluationDatasetList:
    return await EvaluationRepository.list_datasets(
        application_key=application_key,
        cursor=cursor,
        limit=limit,
    )


async def get_dataset(dataset_id: str) -> EvaluationDatasetDetail:
    return await EvaluationRepository.get_dataset(dataset_id)


async def add_case(
    *,
    dataset_id: str,
    request: EvaluationCaseCreate,
    authenticated_user: AuthenticatedUser,
) -> EvaluationCaseRead:
    audit_log(
        "create",
        "evaluation_case",
        None,
        authenticated_user,
        {"dataset_id": dataset_id, "case_key": request.case_key},
    )
    return await EvaluationRepository.add_case(dataset_id=dataset_id, request=request)


async def lock_dataset(
    dataset_id: str,
    authenticated_user: AuthenticatedUser,
) -> EvaluationDatasetRead:
    audit_log("update", "evaluation_dataset", dataset_id, authenticated_user)
    return await EvaluationRepository.lock_dataset(dataset_id)


async def start_run(
    request: EvaluationRunStart,
    authenticated_user: AuthenticatedUser,
) -> EvaluationRunDetail:
    audit_log(
        "create",
        "evaluation_run",
        None,
        authenticated_user,
        {
            "dataset_id": request.dataset_id,
            "request_key": request.request_key,
            "run_label": request.run_label,
        },
    )
    return await EvaluationRepository.start_run(request, authenticated_user)


async def list_runs(
    *,
    scope: EvaluationRunScope,
    cursor: str | None,
    limit: int,
) -> EvaluationRunList:
    return await EvaluationRepository.list_runs(
        scope=scope,
        cursor=cursor,
        limit=limit,
    )


async def get_run(run_id: str) -> EvaluationRunDetail:
    return await EvaluationRepository.get_run(run_id)


async def get_attempt(attempt_id: str) -> EvaluationAttemptDetail:
    return await EvaluationRepository.get_attempt(attempt_id)


async def bind_attempt_execution(
    *,
    attempt_id: str,
    execution: SemanticExecutionReference,
    authenticated_user: AuthenticatedUser,
) -> EvaluationAttemptRead:
    audit_log("update", "evaluation_attempt", attempt_id, authenticated_user)
    return await EvaluationRepository.bind_attempt_execution(
        attempt_id=attempt_id,
        execution=execution,
    )


async def record_attempt_result(
    *,
    attempt_id: str,
    result: EvaluationAttemptResult,
    authenticated_user: AuthenticatedUser,
) -> EvaluationAttemptRead:
    audit_log("update", "evaluation_attempt", attempt_id, authenticated_user)
    return await EvaluationRepository.record_attempt_result(
        attempt_id=attempt_id,
        result=result,
    )


async def find_execution_membership(
    *,
    execution: SemanticExecutionReference,
    cursor: str | None,
    limit: int,
) -> EvaluationExecutionMembershipList:
    return await EvaluationRepository.find_execution_membership(
        execution=execution,
        cursor=cursor,
        limit=limit,
    )
