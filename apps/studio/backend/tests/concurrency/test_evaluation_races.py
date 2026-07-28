"""SQLite write-serialization tests for evaluation state transitions."""

from __future__ import annotations

import asyncio

from app.db_sqlite.users.models import UserTable
from app.features.evaluation.contract import EvaluationConflictError
from app.features.evaluation.repository import EvaluationRepository
from app.features.evaluation.schemas import (
    EvaluationAttemptResult,
    EvaluationCaseCreate,
    EvaluationDatasetCreate,
    EvaluationRunStart,
    SemanticExecutionReference,
)

REVISION = "a" * 40


async def _persist_user(test_db, user) -> None:
    async with test_db() as session:
        session.add(
            UserTable(
                id=user.user_id,
                email=user.email,
                password_hash="test-only",
            )
        )
        await session.commit()


def _case(case_key: str) -> EvaluationCaseCreate:
    return EvaluationCaseCreate(
        case_key=case_key,
        origin="authored",
        target_kind="node",
        target_key="date_response_node",
        input_version=1,
        input_json={"prompt": case_key},
        expectation_json={"rubric": "Names one specific place."},
        evaluator_key="response_quality",
        evaluator_version=1,
    )


async def _draft(test_db, user):
    await _persist_user(test_db, user)
    return await EvaluationRepository.create_dataset(
        EvaluationDatasetCreate(
            application_key="ai_chat",
            key="race_dataset",
            name="Race dataset",
        ),
        user,
    )


async def test_add_case_and_lock_share_one_immediate_write_boundary(
    test_db,
    mock_authenticated_user,
) -> None:
    dataset = await _draft(test_db, mock_authenticated_user)
    results = await asyncio.gather(
        EvaluationRepository.add_case(
            dataset_id=dataset.id,
            request=_case("racing_case"),
        ),
        EvaluationRepository.lock_dataset(dataset.id),
        return_exceptions=True,
    )

    assert any(
        not isinstance(result, Exception) and getattr(result, "status", None) == "locked"
        for result in results
    )
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(failures) <= 1
    if failures:
        assert isinstance(failures[0], EvaluationConflictError)
        assert failures[0].code == "dataset_locked"

    detail = await EvaluationRepository.get_dataset(dataset.id)
    assert detail.dataset.status == "locked"
    assert len(detail.cases) in (0, 1)


async def test_concurrent_final_attempt_updates_complete_run_once(
    test_db,
    mock_authenticated_user,
) -> None:
    dataset = await _draft(test_db, mock_authenticated_user)
    await EvaluationRepository.add_case(dataset_id=dataset.id, request=_case("case_1"))
    await EvaluationRepository.add_case(dataset_id=dataset.id, request=_case("case_2"))
    await EvaluationRepository.lock_dataset(dataset.id)
    run = await EvaluationRepository.start_run(
        EvaluationRunStart(
            dataset_id=dataset.id,
            request_key="concurrent-final-results",
            candidate_label="baseline",
            source_revision=REVISION,
        ),
        mock_authenticated_user,
    )

    for ordinal, run_case in enumerate(run.cases, start=1):
        await EvaluationRepository.bind_attempt_execution(
            attempt_id=run_case.attempt.id,
            execution=SemanticExecutionReference(
                service_namespace="junjo.examples",
                service_name="ai-chat-evaluation",
                executable_type="workflow",
                runtime_id=f"workflow-run-{ordinal}",
            ),
        )

    await asyncio.gather(
        *[
            EvaluationRepository.record_attempt_result(
                attempt_id=run_case.attempt.id,
                result=EvaluationAttemptResult(
                    status="passed",
                    score=1.0,
                    reason="The response names a specific plausible place.",
                ),
            )
            for run_case in run.cases
        ]
    )

    completed = await EvaluationRepository.get_run(run.run.id)
    assert completed.run.status == "completed"
    assert completed.run.completed_at is not None
    assert [item.attempt.status for item in completed.cases] == ["passed", "passed"]


async def test_subject_execution_can_bind_to_only_one_attempt(
    test_db,
    mock_authenticated_user,
) -> None:
    dataset = await _draft(test_db, mock_authenticated_user)
    await EvaluationRepository.add_case(dataset_id=dataset.id, request=_case("case_1"))
    await EvaluationRepository.add_case(dataset_id=dataset.id, request=_case("case_2"))
    await EvaluationRepository.lock_dataset(dataset.id)
    run = await EvaluationRepository.start_run(
        EvaluationRunStart(
            dataset_id=dataset.id,
            request_key="unique-subject-execution",
            candidate_label="baseline",
            source_revision=REVISION,
        ),
        mock_authenticated_user,
    )
    execution = SemanticExecutionReference(
        service_namespace="junjo.examples",
        service_name="ai-chat-evaluation",
        executable_type="workflow",
        runtime_id="one-runtime-id",
    )

    results = await asyncio.gather(
        *[
            EvaluationRepository.bind_attempt_execution(
                attempt_id=run_case.attempt.id,
                execution=execution,
            )
            for run_case in run.cases
        ],
        return_exceptions=True,
    )

    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], EvaluationConflictError)
    assert failures[0].code == "execution_already_bound"
