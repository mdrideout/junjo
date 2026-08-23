"""Canonical repository and state-transition tests for evaluations."""

from __future__ import annotations

from sqlalchemy import delete

from app.db_sqlite.users.models import UserTable
from app.features.evaluation.contract import EvaluationConflictError
from app.features.evaluation.repository import EvaluationRepository
from app.features.evaluation.schemas import (
    EvaluationAttemptResult,
    EvaluationCaseCreate,
    EvaluationDatasetCreate,
    EvaluationRunScope,
    EvaluationRunStart,
    ExecutionEvidenceReference,
    OpenTelemetrySpanReference,
    SemanticExecutionReference,
    TargetKind,
)

REVISION = "a" * 40
OTHER_REVISION = "b" * 40


async def _persist_authenticated_user(test_db, user) -> None:
    async with test_db() as session:
        session.add(
            UserTable(
                id=user.user_id,
                email=user.email,
                password_hash="test-only",
            )
        )
        await session.commit()


def _dataset(name: str = "Local place realism") -> EvaluationDatasetCreate:
    return EvaluationDatasetCreate(
        application_key="ai_chat",
        key="local_place_realism_v1",
        name=name,
        description="Three prompts that require one specific plausible place.",
    )


def _case(
    *,
    case_key: str = "specific_place_1",
    origin: str = "authored",
    source_evidence: ExecutionEvidenceReference | None = None,
    target_kind: TargetKind = "node",
    target_key: str = "date_response_node",
    target_name: str = "CreateDateIdeaResponseNode",
    evaluator_key: str = "response_quality",
    evaluation_name: str = "Response place realism",
) -> EvaluationCaseCreate:
    return EvaluationCaseCreate(
        case_key=case_key,
        evaluation_name=evaluation_name,
        origin=origin,
        target_kind=target_kind,
        target_key=target_key,
        target_name=target_name,
        input_version=1,
        input_json={"prompt": "Name one specific plausible nearby place."},
        expectation_json={"rubric": "Names one specific place."},
        evaluator_key=evaluator_key,
        evaluator_version=1,
        source_evidence=source_evidence,
        source_revision=REVISION if source_evidence else None,
    )


def _run(dataset_id: str) -> EvaluationRunStart:
    return EvaluationRunStart(
        dataset_id=dataset_id,
        request_key="baseline-request",
        run_label="baseline",
        source_revision=REVISION,
    )


async def test_agent_target_case_persists_in_control_database(
    test_db,
    mock_authenticated_user,
) -> None:
    await _persist_authenticated_user(test_db, mock_authenticated_user)
    dataset = await EvaluationRepository.create_dataset(
        _dataset(),
        mock_authenticated_user,
    )
    case = await EvaluationRepository.add_case(
        dataset_id=dataset.id,
        request=_case(target_kind="agent"),
    )
    assert case.target_kind == "agent"


async def test_complete_control_loop_is_idempotent_and_exact(
    test_db,
    mock_authenticated_user,
) -> None:
    await _persist_authenticated_user(test_db, mock_authenticated_user)
    source = SemanticExecutionReference(
        service_namespace="junjo.examples",
        service_name="ai-chat-evaluation",
        executable_type="workflow",
        runtime_id="source-workflow-run",
    )
    dataset = await EvaluationRepository.create_dataset(
        _dataset(),
        mock_authenticated_user,
    )
    assert dataset.status == "draft"

    same_dataset = await EvaluationRepository.create_dataset(
        _dataset(),
        mock_authenticated_user,
    )
    assert same_dataset.id == dataset.id

    case = await EvaluationRepository.add_case(
        dataset_id=dataset.id,
        request=_case(origin="generated", source_evidence=source),
    )
    assert case.ordinal == 1
    assert case.source_evidence == source

    locked = await EvaluationRepository.lock_dataset(dataset.id)
    assert locked.status == "locked"
    assert locked.locked_at is not None
    assert (await EvaluationRepository.lock_dataset(dataset.id)).locked_at == locked.locked_at

    identical_case = await EvaluationRepository.add_case(
        dataset_id=dataset.id,
        request=_case(origin="generated", source_evidence=source),
    )
    assert identical_case.id == case.id

    detail = await EvaluationRepository.start_run(
        _run(dataset.id),
        mock_authenticated_user,
    )
    assert [item.case.id for item in detail.cases] == [case.id]
    attempt_id = detail.cases[0].attempt.id
    assert detail.cases[0].attempt.status == "queued"

    subject = SemanticExecutionReference(
        service_namespace="junjo.examples",
        service_name="ai-chat-evaluation",
        executable_type="workflow",
        runtime_id="subject-workflow-run",
    )
    bound = await EvaluationRepository.bind_attempt_evidence(
        attempt_id=attempt_id,
        evidence=subject,
    )
    assert bound.subject_evidence == subject
    assert bound.evidence_bound_at is not None
    assert (
        await EvaluationRepository.bind_attempt_evidence(
            attempt_id=attempt_id,
            evidence=subject,
        )
    ).evidence_bound_at == bound.evidence_bound_at

    result = EvaluationAttemptResult(
        status="passed",
        reason="The response names a specific plausible place.",
    )
    recorded = await EvaluationRepository.record_attempt_result(
        attempt_id=attempt_id,
        result=result,
    )
    assert recorded.duration_ms is None
    assert recorded.status == "passed"
    assert (
        await EvaluationRepository.record_attempt_result(
            attempt_id=attempt_id,
            result=result,
        )
    ).recorded_at == recorded.recorded_at

    completed = await EvaluationRepository.get_run(detail.run.id)
    assert completed.run.status == "completed"
    assert completed.run.completed_at is not None
    assert completed.cases[0].attempt.subject_evidence == subject

    resumed = await EvaluationRepository.start_run(
        _run(dataset.id),
        mock_authenticated_user,
    )
    assert resumed.run.id == detail.run.id
    assert resumed.cases[0].attempt.status == "passed"

    listed = await EvaluationRepository.list_runs(
        scope=EvaluationRunScope(dataset_id=dataset.id),
        cursor=None,
        limit=50,
    )
    assert len(listed.items) == 1
    assert listed.scope == EvaluationRunScope(dataset_id=dataset.id)
    assert listed.items[0].outcome_summary.model_dump() == {
        "total": 1,
        "queued": 0,
        "judged": 1,
        "passed": 1,
        "failed": 0,
        "error": 0,
        "pass_rate": 1.0,
        "coverage": 1.0,
    }
    assert [facet.model_dump() for facet in listed.items[0].target_facets] == [
        {
            "target_kind": "node",
            "target_key": "date_response_node",
            "target_name": "CreateDateIdeaResponseNode",
            "input_version": 1,
            "case_count": 1,
        }
    ]
    assert [facet.model_dump() for facet in listed.items[0].evaluation_facets] == [
        {
            "evaluation_name": "Response place realism",
            "case_count": 1,
        }
    ]

    source_membership = await EvaluationRepository.find_evidence_membership(
        evidence=source,
        cursor=None,
        limit=50,
    )
    assert [item.role for item in source_membership.items] == ["case_source"]
    assert source_membership.items[0].case_id == case.id

    subject_membership = await EvaluationRepository.find_evidence_membership(
        evidence=subject,
        cursor=None,
        limit=50,
    )
    assert [item.role for item in subject_membership.items] == ["attempt_subject"]
    assert subject_membership.items[0].attempt_id == attempt_id


async def test_external_span_evidence_is_bound_and_reverse_queryable(
    test_db,
    mock_authenticated_user,
) -> None:
    await _persist_authenticated_user(test_db, mock_authenticated_user)
    dataset = await EvaluationRepository.create_dataset(_dataset(), mock_authenticated_user)
    await EvaluationRepository.add_case(dataset_id=dataset.id, request=_case())
    await EvaluationRepository.lock_dataset(dataset.id)
    run = await EvaluationRepository.start_run(_run(dataset.id), mock_authenticated_user)
    attempt_id = run.cases[0].attempt.id
    evidence = OpenTelemetrySpanReference(
        service_namespace="junjo.examples",
        service_name="base-openai-agents",
        trace_id="1" * 32,
        span_id="a" * 16,
    )

    bound = await EvaluationRepository.bind_attempt_evidence(
        attempt_id=attempt_id,
        evidence=evidence,
    )
    membership = await EvaluationRepository.find_evidence_membership(
        evidence=evidence,
        cursor=None,
        limit=50,
    )

    assert bound.subject_evidence == evidence
    assert bound.evidence_bound_at is not None
    assert [item.attempt_id for item in membership.items] == [attempt_id]


async def test_external_span_evidence_can_identify_a_generated_case_source(
    test_db,
    mock_authenticated_user,
) -> None:
    await _persist_authenticated_user(test_db, mock_authenticated_user)
    dataset = await EvaluationRepository.create_dataset(_dataset(), mock_authenticated_user)
    evidence = OpenTelemetrySpanReference(
        service_namespace="junjo.examples",
        service_name="base-openai-agents",
        trace_id="2" * 32,
        span_id="b" * 16,
    )

    case = await EvaluationRepository.add_case(
        dataset_id=dataset.id,
        request=_case(origin="generated", source_evidence=evidence),
    )
    membership = await EvaluationRepository.find_evidence_membership(
        evidence=evidence,
        cursor=None,
        limit=50,
    )

    assert case.source_evidence == evidence
    assert [item.role for item in membership.items] == ["case_source"]
    assert membership.items[0].case_id == case.id


async def test_conflicting_natural_keys_and_terminal_writes_are_rejected(
    test_db,
    mock_authenticated_user,
) -> None:
    await _persist_authenticated_user(test_db, mock_authenticated_user)
    dataset = await EvaluationRepository.create_dataset(
        _dataset(),
        mock_authenticated_user,
    )

    try:
        await EvaluationRepository.create_dataset(
            _dataset(name="Different name"),
            mock_authenticated_user,
        )
    except EvaluationConflictError as error:
        assert error.code == "dataset_identity_conflict"
    else:
        raise AssertionError("conflicting dataset content was accepted")

    case = await EvaluationRepository.add_case(
        dataset_id=dataset.id,
        request=_case(),
    )
    try:
        await EvaluationRepository.add_case(
            dataset_id=dataset.id,
            request=_case(case_key=case.case_key).model_copy(update={"evaluator_version": 2}),
        )
    except EvaluationConflictError as error:
        assert error.code == "case_identity_conflict"
    else:
        raise AssertionError("conflicting case content was accepted")

    await EvaluationRepository.lock_dataset(dataset.id)
    run = await EvaluationRepository.start_run(
        _run(dataset.id),
        mock_authenticated_user,
    )
    try:
        await EvaluationRepository.start_run(
            _run(dataset.id).model_copy(update={"source_revision": OTHER_REVISION}),
            mock_authenticated_user,
        )
    except EvaluationConflictError as error:
        assert error.code == "run_identity_conflict"
    else:
        raise AssertionError("conflicting run content was accepted")

    attempt_id = run.cases[0].attempt.id
    execution = SemanticExecutionReference(
        service_namespace="",
        service_name="ai-chat-evaluation",
        executable_type="workflow",
        runtime_id="workflow-run",
    )
    await EvaluationRepository.bind_attempt_evidence(
        attempt_id=attempt_id,
        evidence=execution,
    )
    try:
        await EvaluationRepository.bind_attempt_evidence(
            attempt_id=attempt_id,
            evidence=execution.model_copy(update={"runtime_id": "other-run"}),
        )
    except EvaluationConflictError as error:
        assert error.code == "attempt_evidence_conflict"
    else:
        raise AssertionError("conflicting execution binding was accepted")

    await EvaluationRepository.record_attempt_result(
        attempt_id=attempt_id,
        result=EvaluationAttemptResult(
            status="failed",
            reason="The response did not name a specific place.",
            duration_ms=20,
        ),
    )
    try:
        await EvaluationRepository.record_attempt_result(
            attempt_id=attempt_id,
            result=EvaluationAttemptResult(
                status="passed",
                reason="Conflicting outcome.",
                duration_ms=20,
            ),
        )
    except EvaluationConflictError as error:
        assert error.code == "attempt_result_conflict"
    else:
        raise AssertionError("conflicting terminal result was accepted")


async def test_draft_cannot_run_and_locked_dataset_cannot_gain_new_case(
    test_db,
    mock_authenticated_user,
) -> None:
    await _persist_authenticated_user(test_db, mock_authenticated_user)
    dataset = await EvaluationRepository.create_dataset(
        _dataset(),
        mock_authenticated_user,
    )
    await EvaluationRepository.add_case(dataset_id=dataset.id, request=_case())

    try:
        await EvaluationRepository.start_run(_run(dataset.id), mock_authenticated_user)
    except EvaluationConflictError as error:
        assert error.code == "dataset_not_locked"
    else:
        raise AssertionError("draft dataset started a run")

    await EvaluationRepository.lock_dataset(dataset.id)
    try:
        await EvaluationRepository.add_case(
            dataset_id=dataset.id,
            request=_case(case_key="new_case"),
        )
    except EvaluationConflictError as error:
        assert error.code == "dataset_locked"
    else:
        raise AssertionError("locked dataset accepted a new case")


async def test_case_count_is_bounded_inside_serialized_write(
    test_db,
    mock_authenticated_user,
    monkeypatch,
) -> None:
    await _persist_authenticated_user(test_db, mock_authenticated_user)
    monkeypatch.setattr(
        "app.features.evaluation.repository.MAX_CASES_PER_DATASET",
        1,
    )
    dataset = await EvaluationRepository.create_dataset(
        _dataset(),
        mock_authenticated_user,
    )
    await EvaluationRepository.add_case(dataset_id=dataset.id, request=_case())

    try:
        await EvaluationRepository.add_case(
            dataset_id=dataset.id,
            request=_case(case_key="over_limit"),
        )
    except EvaluationConflictError as error:
        assert error.code == "dataset_case_limit_reached"
    else:
        raise AssertionError("dataset accepted more cases than its declared limit")


async def test_error_without_execution_is_terminal_and_preserves_history_after_user_delete(
    test_db,
    mock_authenticated_user,
) -> None:
    await _persist_authenticated_user(test_db, mock_authenticated_user)
    dataset = await EvaluationRepository.create_dataset(
        _dataset(),
        mock_authenticated_user,
    )
    await EvaluationRepository.add_case(dataset_id=dataset.id, request=_case())
    await EvaluationRepository.lock_dataset(dataset.id)
    run = await EvaluationRepository.start_run(_run(dataset.id), mock_authenticated_user)
    attempt_id = run.cases[0].attempt.id

    recorded = await EvaluationRepository.record_attempt_result(
        attempt_id=attempt_id,
        result=EvaluationAttemptResult(
            status="error",
            reason="Target setup failed before execution identity existed.",
        ),
    )
    assert recorded.subject_evidence is None
    assert recorded.status == "error"

    async with test_db() as session:
        await session.execute(
            delete(UserTable).where(UserTable.id == mock_authenticated_user.user_id)
        )
        await session.commit()

    preserved = await EvaluationRepository.get_run(run.run.id)
    assert preserved.dataset.created_by_user_id is None
    assert preserved.run.created_by_user_id is None
    assert preserved.cases[0].attempt.status == "error"


async def test_dataset_run_and_membership_keyset_pages_do_not_repeat_rows(
    test_db,
    mock_authenticated_user,
) -> None:
    await _persist_authenticated_user(test_db, mock_authenticated_user)
    datasets = []
    for index in range(3):
        datasets.append(
            await EvaluationRepository.create_dataset(
                EvaluationDatasetCreate(
                    application_key="ai_chat",
                    key=f"page_dataset_{index}",
                    name=f"Page dataset {index}",
                ),
                mock_authenticated_user,
            )
        )

    first_datasets = await EvaluationRepository.list_datasets(
        application_key="ai_chat",
        cursor=None,
        limit=2,
    )
    assert len(first_datasets.items) == 2
    assert first_datasets.next_cursor is not None
    second_datasets = await EvaluationRepository.list_datasets(
        application_key="ai_chat",
        cursor=first_datasets.next_cursor,
        limit=2,
    )
    assert len(second_datasets.items) == 1
    assert {item.id for item in first_datasets.items + second_datasets.items} == {
        dataset.id for dataset in datasets
    }

    source = SemanticExecutionReference(
        service_namespace="junjo.examples",
        service_name="ai-chat-evaluation",
        executable_type="workflow",
        runtime_id="shared-source-run",
    )
    selected = datasets[0]
    for index in range(2):
        await EvaluationRepository.add_case(
            dataset_id=selected.id,
            request=_case(
                case_key=f"generated_{index}",
                origin="generated",
                source_evidence=source,
            ),
        )
    await EvaluationRepository.lock_dataset(selected.id)
    for index in range(2):
        await EvaluationRepository.start_run(
            EvaluationRunStart(
                dataset_id=selected.id,
                request_key=f"run_page_{index}",
                run_label=f"candidate {index}",
                source_revision=REVISION,
            ),
            mock_authenticated_user,
        )

    first_runs = await EvaluationRepository.list_runs(
        scope=EvaluationRunScope(dataset_id=selected.id),
        cursor=None,
        limit=1,
    )
    second_runs = await EvaluationRepository.list_runs(
        scope=EvaluationRunScope(dataset_id=selected.id),
        cursor=first_runs.next_cursor,
        limit=1,
    )
    assert first_runs.next_cursor is not None
    assert second_runs.next_cursor is None
    assert first_runs.items[0].run.id != second_runs.items[0].run.id

    first_membership = await EvaluationRepository.find_evidence_membership(
        evidence=source,
        cursor=None,
        limit=1,
    )
    second_membership = await EvaluationRepository.find_evidence_membership(
        evidence=source,
        cursor=first_membership.next_cursor,
        limit=1,
    )
    assert first_membership.next_cursor is not None
    assert second_membership.next_cursor is None
    assert first_membership.items[0].case_id != second_membership.items[0].case_id


async def test_run_scope_filters_must_match_the_same_case(
    test_db,
    mock_authenticated_user,
) -> None:
    await _persist_authenticated_user(test_db, mock_authenticated_user)
    dataset = await EvaluationRepository.create_dataset(
        EvaluationDatasetCreate(
            application_key="ai_chat",
            key="mixed_targets",
            name="Mixed targets",
        ),
        mock_authenticated_user,
    )
    await EvaluationRepository.add_case(
        dataset_id=dataset.id,
        request=_case(
            case_key="node_case",
            target_kind="node",
            target_key="date_response_node",
            evaluator_key="node_quality",
            evaluation_name="Node place realism",
        ),
    )
    await EvaluationRepository.add_case(
        dataset_id=dataset.id,
        request=_case(
            case_key="agent_case",
            target_kind="agent",
            target_key="chat_agent",
            target_name="AI Chat Agent",
            evaluator_key="agent_quality",
            evaluation_name="Agent place realism",
        ),
    )
    await EvaluationRepository.lock_dataset(dataset.id)
    await EvaluationRepository.start_run(
        _run(dataset.id),
        mock_authenticated_user,
    )

    impossible_scope = await EvaluationRepository.list_runs(
        scope=EvaluationRunScope(
            dataset_id=dataset.id,
            target_kind="node",
            evaluation_name="Agent place realism",
        ),
        cursor=None,
        limit=50,
    )
    assert impossible_scope.items == []

    node_scope = await EvaluationRepository.list_runs(
        scope=EvaluationRunScope(
            dataset_id=dataset.id,
            target_kind="node",
            target_key="date_response_node",
            input_version=1,
            evaluation_name="Node place realism",
        ),
        cursor=None,
        limit=50,
    )
    assert node_scope.items[0].outcome_summary.model_dump() == {
        "total": 1,
        "queued": 1,
        "judged": 0,
        "passed": 0,
        "failed": 0,
        "error": 0,
        "pass_rate": None,
        "coverage": 0.0,
    }
    assert len(node_scope.items[0].target_facets) == 2
