"""Transactional SQLite repository for evaluation control records."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import String, and_, func, literal, null, or_, select, text, union_all
from sqlalchemy.exc import IntegrityError

from app.common.datetime_utils import utcnow
from app.db_sqlite import db_config
from app.db_sqlite.evaluation.models import (
    EvaluationCaseAttemptTable,
    EvaluationCaseTable,
    EvaluationDatasetTable,
    EvaluationRunTable,
)
from app.features.auth.models import AuthenticatedUser
from app.features.evaluation.contract import (
    EvaluationConflictError,
    EvaluationNotFoundError,
)
from app.features.evaluation.pagination import (
    MembershipCursor,
    TimeCursor,
    decode_membership_cursor,
    decode_time_cursor,
    encode_membership_cursor,
    encode_time_cursor,
)
from app.features.evaluation.schemas import (
    MAX_CASES_PER_DATASET,
    EvaluationAttemptCounts,
    EvaluationAttemptDetail,
    EvaluationAttemptRead,
    EvaluationAttemptResult,
    EvaluationCaseCreate,
    EvaluationCaseRead,
    EvaluationDatasetCreate,
    EvaluationDatasetDetail,
    EvaluationDatasetList,
    EvaluationDatasetRead,
    EvaluationDatasetSummary,
    EvaluationExecutionMembership,
    EvaluationExecutionMembershipList,
    EvaluationRunCase,
    EvaluationRunDetail,
    EvaluationRunList,
    EvaluationRunRead,
    EvaluationRunStart,
    EvaluationRunSummary,
    SemanticExecutionReference,
    dump_bounded_json,
    load_stored_json,
)


def _db_now():
    """Return the whole-second UTC precision persisted by UTCDateTime."""
    return utcnow().replace(microsecond=0)


def _dataset_summary(row: EvaluationDatasetTable) -> EvaluationDatasetSummary:
    return EvaluationDatasetSummary(
        id=row.id,
        application_key=row.application_key,
        key=row.key,
        name=row.name,
        status=row.status,
    )


def _dataset_read(row: EvaluationDatasetTable) -> EvaluationDatasetRead:
    return EvaluationDatasetRead(
        **_dataset_summary(row).model_dump(),
        description=row.description,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        locked_at=row.locked_at,
    )


def _execution_reference(
    *,
    service_namespace: str | None,
    service_name: str | None,
    executable_type: str | None,
    runtime_id: str | None,
) -> SemanticExecutionReference | None:
    if runtime_id is None:
        return None
    return SemanticExecutionReference(
        service_namespace=service_namespace,
        service_name=service_name,
        executable_type=executable_type,
        runtime_id=runtime_id,
    )


def _case_read(row: EvaluationCaseTable) -> EvaluationCaseRead:
    return EvaluationCaseRead(
        id=row.id,
        dataset_id=row.dataset_id,
        case_key=row.case_key,
        ordinal=row.ordinal,
        origin=row.origin,
        target_kind=row.target_kind,
        target_key=row.target_key,
        input_version=row.input_version,
        input_json=load_stored_json(row.input_json),
        expectation_json=(
            load_stored_json(row.expectation_json) if row.expectation_json is not None else None
        ),
        evaluator_key=row.evaluator_key,
        evaluator_version=row.evaluator_version,
        source_execution=_execution_reference(
            service_namespace=row.source_service_namespace,
            service_name=row.source_service_name,
            executable_type=row.source_executable_type,
            runtime_id=row.source_runtime_id,
        ),
        source_revision=row.source_revision,
        created_at=row.created_at,
    )


def _run_read(row: EvaluationRunTable) -> EvaluationRunRead:
    return EvaluationRunRead(
        id=row.id,
        dataset_id=row.dataset_id,
        request_key=row.request_key,
        candidate_label=row.candidate_label,
        source_revision=row.source_revision,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _attempt_read(row: EvaluationCaseAttemptTable) -> EvaluationAttemptRead:
    return EvaluationAttemptRead(
        id=row.id,
        run_id=row.run_id,
        case_id=row.case_id,
        status=row.status,
        score=row.score,
        reason=row.reason,
        duration_ms=row.duration_ms,
        subject_execution=_execution_reference(
            service_namespace=row.subject_service_namespace,
            service_name=row.subject_service_name,
            executable_type=row.subject_executable_type,
            runtime_id=row.subject_runtime_id,
        ),
        execution_bound_at=row.execution_bound_at,
        recorded_at=row.recorded_at,
    )


def _same_dataset(
    row: EvaluationDatasetTable,
    request: EvaluationDatasetCreate,
) -> bool:
    return (
        row.application_key == request.application_key
        and row.key == request.key
        and row.name == request.name
        and row.description == request.description
    )


def _case_storage_values(request: EvaluationCaseCreate) -> dict[str, object]:
    source = request.source_execution
    return {
        "case_key": request.case_key,
        "origin": request.origin,
        "target_kind": request.target_kind,
        "target_key": request.target_key,
        "input_version": request.input_version,
        "input_json": dump_bounded_json(request.input_json),
        "expectation_json": (
            dump_bounded_json(request.expectation_json)
            if request.expectation_json is not None
            else None
        ),
        "evaluator_key": request.evaluator_key,
        "evaluator_version": request.evaluator_version,
        "source_service_namespace": source.service_namespace if source else None,
        "source_service_name": source.service_name if source else None,
        "source_executable_type": source.executable_type if source else None,
        "source_runtime_id": source.runtime_id if source else None,
        "source_revision": request.source_revision,
    }


def _same_case(
    row: EvaluationCaseTable,
    values: dict[str, object],
) -> bool:
    return all(getattr(row, field) == value for field, value in values.items())


class EvaluationRepository:
    """Static, per-operation session access to canonical evaluation state."""

    @staticmethod
    async def create_dataset(
        request: EvaluationDatasetCreate,
        authenticated_user: AuthenticatedUser,
    ) -> EvaluationDatasetRead:
        async with db_config.async_session() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            existing = (
                await session.execute(
                    select(EvaluationDatasetTable).where(
                        EvaluationDatasetTable.application_key == request.application_key,
                        EvaluationDatasetTable.key == request.key,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                if _same_dataset(existing, request):
                    return _dataset_read(existing)
                raise EvaluationConflictError(
                    "dataset_identity_conflict",
                    "Dataset key already exists with different content.",
                )

            row = EvaluationDatasetTable(
                application_key=request.application_key,
                key=request.key,
                name=request.name,
                description=request.description,
                created_by_user_id=authenticated_user.user_id,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _dataset_read(row)

    @staticmethod
    async def list_datasets(
        *,
        application_key: str,
        cursor: str | None,
        limit: int,
    ) -> EvaluationDatasetList:
        decoded = decode_time_cursor("datasets", cursor)
        async with db_config.async_session() as session:
            stmt = select(EvaluationDatasetTable).where(
                EvaluationDatasetTable.application_key == application_key
            )
            if decoded is not None:
                stmt = stmt.where(
                    or_(
                        EvaluationDatasetTable.created_at < decoded.created_at,
                        and_(
                            EvaluationDatasetTable.created_at == decoded.created_at,
                            EvaluationDatasetTable.id < decoded.record_id,
                        ),
                    )
                )
            stmt = stmt.order_by(
                EvaluationDatasetTable.created_at.desc(),
                EvaluationDatasetTable.id.desc(),
            ).limit(limit + 1)
            rows = list((await session.execute(stmt)).scalars().all())

        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = encode_time_cursor(
                "datasets",
                TimeCursor(created_at=last.created_at, record_id=last.id),
            )
        return EvaluationDatasetList(
            items=[_dataset_read(row) for row in page],
            next_cursor=next_cursor,
        )

    @staticmethod
    async def get_dataset(dataset_id: str) -> EvaluationDatasetDetail:
        async with db_config.async_session() as session:
            dataset = await session.get(EvaluationDatasetTable, dataset_id)
            if dataset is None:
                raise EvaluationNotFoundError("Dataset")
            cases = list(
                (
                    await session.execute(
                        select(EvaluationCaseTable)
                        .where(EvaluationCaseTable.dataset_id == dataset_id)
                        .order_by(
                            EvaluationCaseTable.ordinal,
                            EvaluationCaseTable.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            return EvaluationDatasetDetail(
                dataset=_dataset_read(dataset),
                cases=[_case_read(case) for case in cases],
            )

    @staticmethod
    async def add_case(
        *,
        dataset_id: str,
        request: EvaluationCaseCreate,
    ) -> EvaluationCaseRead:
        values = _case_storage_values(request)
        async with db_config.async_session() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            dataset = await session.get(EvaluationDatasetTable, dataset_id)
            if dataset is None:
                raise EvaluationNotFoundError("Dataset")

            existing = (
                await session.execute(
                    select(EvaluationCaseTable).where(
                        EvaluationCaseTable.dataset_id == dataset_id,
                        EvaluationCaseTable.case_key == request.case_key,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                if _same_case(existing, values):
                    return _case_read(existing)
                raise EvaluationConflictError(
                    "case_identity_conflict",
                    "Case key already exists with different content.",
                )
            if dataset.status != "draft":
                raise EvaluationConflictError(
                    "dataset_locked",
                    "Locked datasets cannot accept new cases.",
                )

            case_count = (
                await session.execute(
                    select(func.count())
                    .select_from(EvaluationCaseTable)
                    .where(EvaluationCaseTable.dataset_id == dataset_id)
                )
            ).scalar_one()
            if case_count >= MAX_CASES_PER_DATASET:
                raise EvaluationConflictError(
                    "dataset_case_limit_reached",
                    f"A dataset may contain at most {MAX_CASES_PER_DATASET} cases.",
                )

            ordinal = case_count + 1
            row = EvaluationCaseTable(
                dataset_id=dataset_id,
                ordinal=ordinal,
                **values,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _case_read(row)

    @staticmethod
    async def lock_dataset(dataset_id: str) -> EvaluationDatasetRead:
        async with db_config.async_session() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            dataset = await session.get(EvaluationDatasetTable, dataset_id)
            if dataset is None:
                raise EvaluationNotFoundError("Dataset")
            if dataset.status == "locked":
                return _dataset_read(dataset)
            dataset.status = "locked"
            dataset.locked_at = _db_now()
            await session.commit()
            return _dataset_read(dataset)

    @staticmethod
    async def start_run(
        request: EvaluationRunStart,
        authenticated_user: AuthenticatedUser,
    ) -> EvaluationRunDetail:
        run_id: str
        async with db_config.async_session() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            dataset = await session.get(EvaluationDatasetTable, request.dataset_id)
            if dataset is None:
                raise EvaluationNotFoundError("Dataset")

            existing = (
                await session.execute(
                    select(EvaluationRunTable).where(
                        EvaluationRunTable.dataset_id == request.dataset_id,
                        EvaluationRunTable.request_key == request.request_key,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                if (
                    existing.candidate_label == request.candidate_label
                    and existing.source_revision == request.source_revision
                ):
                    run_id = existing.id
                else:
                    raise EvaluationConflictError(
                        "run_identity_conflict",
                        "Run request key already exists with different content.",
                    )
            else:
                if dataset.status != "locked":
                    raise EvaluationConflictError(
                        "dataset_not_locked",
                        "A run may start only from a locked dataset.",
                    )
                cases = list(
                    (
                        await session.execute(
                            select(EvaluationCaseTable)
                            .where(EvaluationCaseTable.dataset_id == request.dataset_id)
                            .order_by(
                                EvaluationCaseTable.ordinal,
                                EvaluationCaseTable.id,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if not cases:
                    raise EvaluationConflictError(
                        "dataset_empty",
                        "A run requires at least one dataset case.",
                    )

                run = EvaluationRunTable(
                    dataset_id=request.dataset_id,
                    request_key=request.request_key,
                    candidate_label=request.candidate_label,
                    source_revision=request.source_revision,
                    created_by_user_id=authenticated_user.user_id,
                )
                session.add(run)
                await session.flush()
                run_id = run.id
                session.add_all(
                    [EvaluationCaseAttemptTable(run_id=run_id, case_id=case.id) for case in cases]
                )
                await session.commit()

        return await EvaluationRepository.get_run(run_id)

    @staticmethod
    async def get_run(run_id: str) -> EvaluationRunDetail:
        async with db_config.async_session() as session:
            run = await session.get(EvaluationRunTable, run_id)
            if run is None:
                raise EvaluationNotFoundError("Run")
            dataset = await session.get(EvaluationDatasetTable, run.dataset_id)
            if dataset is None:
                raise RuntimeError("Evaluation run references a missing dataset")
            pairs = list(
                (
                    await session.execute(
                        select(EvaluationCaseTable, EvaluationCaseAttemptTable)
                        .join(
                            EvaluationCaseAttemptTable,
                            and_(
                                EvaluationCaseAttemptTable.case_id == EvaluationCaseTable.id,
                                EvaluationCaseAttemptTable.run_id == run.id,
                            ),
                        )
                        .where(EvaluationCaseTable.dataset_id == run.dataset_id)
                        .order_by(
                            EvaluationCaseTable.ordinal,
                            EvaluationCaseTable.id,
                        )
                    )
                ).all()
            )
            return EvaluationRunDetail(
                run=_run_read(run),
                dataset=_dataset_read(dataset),
                cases=[
                    EvaluationRunCase(
                        case=_case_read(case),
                        attempt=_attempt_read(attempt),
                    )
                    for case, attempt in pairs
                ],
            )

    @staticmethod
    async def list_runs(
        *,
        dataset_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> EvaluationRunList:
        decoded = decode_time_cursor("runs", cursor)
        async with db_config.async_session() as session:
            stmt = select(EvaluationRunTable, EvaluationDatasetTable).join(
                EvaluationDatasetTable,
                EvaluationDatasetTable.id == EvaluationRunTable.dataset_id,
            )
            if dataset_id is not None:
                stmt = stmt.where(EvaluationRunTable.dataset_id == dataset_id)
            if decoded is not None:
                stmt = stmt.where(
                    or_(
                        EvaluationRunTable.created_at < decoded.created_at,
                        and_(
                            EvaluationRunTable.created_at == decoded.created_at,
                            EvaluationRunTable.id < decoded.record_id,
                        ),
                    )
                )
            stmt = stmt.order_by(
                EvaluationRunTable.created_at.desc(),
                EvaluationRunTable.id.desc(),
            ).limit(limit + 1)
            rows = list((await session.execute(stmt)).all())
            page = rows[:limit]

            counts: dict[str, dict[str, int]] = defaultdict(
                lambda: {
                    "queued": 0,
                    "passed": 0,
                    "failed": 0,
                    "error": 0,
                }
            )
            run_ids = [run.id for run, _dataset in page]
            if run_ids:
                count_rows = (
                    await session.execute(
                        select(
                            EvaluationCaseAttemptTable.run_id,
                            EvaluationCaseAttemptTable.status,
                            func.count(),
                        )
                        .where(EvaluationCaseAttemptTable.run_id.in_(run_ids))
                        .group_by(
                            EvaluationCaseAttemptTable.run_id,
                            EvaluationCaseAttemptTable.status,
                        )
                    )
                ).all()
                for counted_run_id, status, count in count_rows:
                    counts[counted_run_id][status] = count

        next_cursor = None
        if len(rows) > limit and page:
            last_run = page[-1][0]
            next_cursor = encode_time_cursor(
                "runs",
                TimeCursor(created_at=last_run.created_at, record_id=last_run.id),
            )
        items: list[EvaluationRunSummary] = []
        for run, dataset in page:
            status_counts = counts[run.id]
            items.append(
                EvaluationRunSummary(
                    run=_run_read(run),
                    dataset=_dataset_summary(dataset),
                    attempt_counts=EvaluationAttemptCounts(
                        total=sum(status_counts.values()),
                        **status_counts,
                    ),
                )
            )
        return EvaluationRunList(items=items, next_cursor=next_cursor)

    @staticmethod
    async def get_attempt(attempt_id: str) -> EvaluationAttemptDetail:
        async with db_config.async_session() as session:
            row = (
                await session.execute(
                    select(
                        EvaluationCaseAttemptTable,
                        EvaluationRunTable,
                        EvaluationDatasetTable,
                        EvaluationCaseTable,
                    )
                    .join(
                        EvaluationRunTable,
                        EvaluationRunTable.id == EvaluationCaseAttemptTable.run_id,
                    )
                    .join(
                        EvaluationDatasetTable,
                        EvaluationDatasetTable.id == EvaluationRunTable.dataset_id,
                    )
                    .join(
                        EvaluationCaseTable,
                        EvaluationCaseTable.id == EvaluationCaseAttemptTable.case_id,
                    )
                    .where(EvaluationCaseAttemptTable.id == attempt_id)
                )
            ).one_or_none()
            if row is None:
                raise EvaluationNotFoundError("Attempt")
            attempt, run, dataset, case = row
            return EvaluationAttemptDetail(
                run=_run_read(run),
                dataset=_dataset_read(dataset),
                case=_case_read(case),
                attempt=_attempt_read(attempt),
            )

    @staticmethod
    async def bind_attempt_execution(
        *,
        attempt_id: str,
        execution: SemanticExecutionReference,
    ) -> EvaluationAttemptRead:
        try:
            async with db_config.async_session() as session:
                await session.execute(text("BEGIN IMMEDIATE"))
                attempt = await session.get(EvaluationCaseAttemptTable, attempt_id)
                if attempt is None:
                    raise EvaluationNotFoundError("Attempt")
                current = _execution_reference(
                    service_namespace=attempt.subject_service_namespace,
                    service_name=attempt.subject_service_name,
                    executable_type=attempt.subject_executable_type,
                    runtime_id=attempt.subject_runtime_id,
                )
                if current is not None:
                    if current == execution:
                        return _attempt_read(attempt)
                    raise EvaluationConflictError(
                        "attempt_execution_conflict",
                        "Attempt is already bound to a different execution.",
                    )
                if attempt.status != "queued":
                    raise EvaluationConflictError(
                        "attempt_terminal",
                        "A terminal attempt cannot acquire an execution binding.",
                    )

                attempt.subject_service_namespace = execution.service_namespace
                attempt.subject_service_name = execution.service_name
                attempt.subject_executable_type = execution.executable_type
                attempt.subject_runtime_id = execution.runtime_id
                attempt.execution_bound_at = _db_now()
                await session.commit()
                return _attempt_read(attempt)
        except IntegrityError as error:
            raise EvaluationConflictError(
                "execution_already_bound",
                "Execution is already bound to another attempt.",
            ) from error

    @staticmethod
    async def record_attempt_result(
        *,
        attempt_id: str,
        result: EvaluationAttemptResult,
    ) -> EvaluationAttemptRead:
        async with db_config.async_session() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            attempt = await session.get(EvaluationCaseAttemptTable, attempt_id)
            if attempt is None:
                raise EvaluationNotFoundError("Attempt")
            if attempt.status != "queued":
                if (
                    attempt.status == result.status
                    and attempt.score == result.score
                    and attempt.reason == result.reason
                    and attempt.duration_ms == result.duration_ms
                ):
                    return _attempt_read(attempt)
                raise EvaluationConflictError(
                    "attempt_result_conflict",
                    "Attempt already has a different terminal result.",
                )
            if result.status in ("passed", "failed") and attempt.subject_runtime_id is None:
                raise EvaluationConflictError(
                    "attempt_execution_required",
                    "Passed and failed attempts require a bound execution.",
                )

            attempt.status = result.status
            attempt.score = result.score
            attempt.reason = result.reason
            attempt.duration_ms = result.duration_ms
            attempt.recorded_at = _db_now()
            await session.flush()

            queued_count = (
                await session.execute(
                    select(func.count())
                    .select_from(EvaluationCaseAttemptTable)
                    .where(
                        EvaluationCaseAttemptTable.run_id == attempt.run_id,
                        EvaluationCaseAttemptTable.status == "queued",
                    )
                )
            ).scalar_one()
            if queued_count == 0:
                run = await session.get(EvaluationRunTable, attempt.run_id)
                if run is None:
                    raise RuntimeError("Evaluation attempt references a missing run")
                if run.status == "active":
                    run.status = "completed"
                    run.completed_at = _db_now()

            await session.commit()
            return _attempt_read(attempt)

    @staticmethod
    async def find_execution_membership(
        *,
        execution: SemanticExecutionReference,
        cursor: str | None,
        limit: int,
    ) -> EvaluationExecutionMembershipList:
        decoded = decode_membership_cursor(cursor)
        source = select(
            literal("case_source").label("role"),
            EvaluationCaseTable.id.label("record_id"),
            EvaluationCaseTable.dataset_id.label("dataset_id"),
            EvaluationCaseTable.id.label("case_id"),
            null().cast(String).label("run_id"),
            null().cast(String).label("attempt_id"),
        ).where(
            EvaluationCaseTable.source_service_namespace == execution.service_namespace,
            EvaluationCaseTable.source_service_name == execution.service_name,
            EvaluationCaseTable.source_executable_type == execution.executable_type,
            EvaluationCaseTable.source_runtime_id == execution.runtime_id,
        )
        subject = (
            select(
                literal("attempt_subject").label("role"),
                EvaluationCaseAttemptTable.id.label("record_id"),
                EvaluationRunTable.dataset_id.label("dataset_id"),
                EvaluationCaseAttemptTable.case_id.label("case_id"),
                EvaluationCaseAttemptTable.run_id.label("run_id"),
                EvaluationCaseAttemptTable.id.label("attempt_id"),
            )
            .join(
                EvaluationRunTable,
                EvaluationRunTable.id == EvaluationCaseAttemptTable.run_id,
            )
            .where(
                EvaluationCaseAttemptTable.subject_service_namespace == execution.service_namespace,
                EvaluationCaseAttemptTable.subject_service_name == execution.service_name,
                EvaluationCaseAttemptTable.subject_executable_type == execution.executable_type,
                EvaluationCaseAttemptTable.subject_runtime_id == execution.runtime_id,
            )
        )
        memberships = union_all(source, subject).subquery()
        stmt = select(memberships)
        if decoded is not None:
            stmt = stmt.where(
                or_(
                    memberships.c.role > decoded.role,
                    and_(
                        memberships.c.role == decoded.role,
                        memberships.c.record_id > decoded.record_id,
                    ),
                )
            )
        stmt = stmt.order_by(
            memberships.c.role,
            memberships.c.record_id,
        ).limit(limit + 1)

        async with db_config.async_session() as session:
            rows = list((await session.execute(stmt)).mappings().all())

        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit and page:
            last = page[-1]
            next_cursor = encode_membership_cursor(
                MembershipCursor(role=last["role"], record_id=last["record_id"])
            )
        return EvaluationExecutionMembershipList(
            items=[
                EvaluationExecutionMembership(
                    role=row["role"],
                    dataset_id=row["dataset_id"],
                    case_id=row["case_id"],
                    run_id=row["run_id"],
                    attempt_id=row["attempt_id"],
                )
                for row in page
            ],
            next_cursor=next_cursor,
        )
