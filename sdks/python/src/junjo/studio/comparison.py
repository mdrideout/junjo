"""Deterministic baseline/candidate projection over Studio run details."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .errors import RunComparisonError
from .models import (
    MAX_CASES_PER_DATASET,
    AttemptRead,
    AttemptStatus,
    CaseRead,
    DatasetRead,
    RunDetail,
    RunRead,
    RunScope,
    StudioDto,
)


class RunComparisonTransition(StrEnum):
    """Deterministic candidate transition relative to a baseline attempt."""

    IMPROVED = "improved"
    REGRESSED = "regressed"
    NEWLY_ERRORED = "newly_errored"
    RECOVERED = "recovered"
    UNCHANGED = "unchanged"
    CHANGED = "changed"


class RunComparisonSummary(StudioDto):
    """Outcome counts for one side of a comparison."""

    total: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    judged: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    passed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    failed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    error: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    queued: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class RunComparisonTransitionCounts(StudioDto):
    """Counts for every supported transition category."""

    improved: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    regressed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    newly_errored: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    recovered: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    unchanged: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    changed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)


class RunComparisonRow(StudioDto):
    """One exact dataset case aligned across baseline and candidate runs."""

    case: CaseRead
    baseline_attempt: AttemptRead
    candidate_attempt: AttemptRead
    transition: RunComparisonTransition
    duration_delta_ms: int | None


class RunComparison(StudioDto):
    """Comparison of two revisions evaluated against one locked dataset."""

    dataset: DatasetRead
    scope: RunScope
    baseline_run: RunRead
    candidate_run: RunRead
    baseline_summary: RunComparisonSummary
    candidate_summary: RunComparisonSummary
    transition_counts: RunComparisonTransitionCounts
    rows: tuple[RunComparisonRow, ...] = Field(max_length=MAX_CASES_PER_DATASET)


def _transition(
    baseline: AttemptRead,
    candidate: AttemptRead,
) -> RunComparisonTransition:
    if baseline.status is AttemptStatus.FAILED and candidate.status is AttemptStatus.PASSED:
        return RunComparisonTransition.IMPROVED
    if baseline.status is AttemptStatus.PASSED and candidate.status is AttemptStatus.FAILED:
        return RunComparisonTransition.REGRESSED
    if baseline.status is not AttemptStatus.ERROR and candidate.status is AttemptStatus.ERROR:
        return RunComparisonTransition.NEWLY_ERRORED
    if baseline.status is AttemptStatus.ERROR and candidate.status is not AttemptStatus.ERROR:
        return RunComparisonTransition.RECOVERED
    if baseline.status is candidate.status:
        return RunComparisonTransition.UNCHANGED
    return RunComparisonTransition.CHANGED


def _summary(attempts: list[AttemptRead]) -> RunComparisonSummary:
    counts = {
        AttemptStatus.QUEUED: 0,
        AttemptStatus.PASSED: 0,
        AttemptStatus.FAILED: 0,
        AttemptStatus.ERROR: 0,
    }
    for attempt in attempts:
        counts[attempt.status] += 1
    judged = counts[AttemptStatus.PASSED] + counts[AttemptStatus.FAILED]
    return RunComparisonSummary(
        total=len(attempts),
        judged=judged,
        passed=counts[AttemptStatus.PASSED],
        failed=counts[AttemptStatus.FAILED],
        error=counts[AttemptStatus.ERROR],
        queued=counts[AttemptStatus.QUEUED],
        pass_rate=counts[AttemptStatus.PASSED] / judged if judged else None,
    )


def _case_matches_scope(case: CaseRead, scope: RunScope) -> bool:
    return (
        (scope.target_kind is None or case.target_kind is scope.target_kind)
        and (scope.target_key is None or case.target_key == scope.target_key)
        and (scope.input_version is None or case.input_version == scope.input_version)
        and (scope.evaluation_name is None or case.evaluation_name == scope.evaluation_name)
    )


def project_run_comparison(
    baseline: RunDetail,
    candidate: RunDetail,
    *,
    scope: RunScope | None = None,
) -> RunComparison:
    """Align two run details by immutable case identity.

    Duration deltas are candidate minus baseline. Missing duration values
    remain ``None`` rather than being interpreted as zero.

    :param baseline: Baseline run detail returned by Studio.
    :param candidate: Candidate run detail returned by Studio.
    :return: Ordinally ordered comparison rows.
    :raises RunComparisonError: If the runs or case memberships cannot be
        paired exactly.
    """

    if baseline.run.id == candidate.run.id:
        raise RunComparisonError("Baseline and candidate run IDs must differ.")
    if baseline.dataset.id != candidate.dataset.id:
        raise RunComparisonError("Evaluation runs must use the same locked dataset.")
    comparison_scope = scope or RunScope(dataset_id=baseline.dataset.id)
    if comparison_scope.dataset_id not in (None, baseline.dataset.id):
        raise RunComparisonError("Comparison scope must use the runs' locked dataset.")
    comparison_scope = comparison_scope.model_copy(update={"dataset_id": baseline.dataset.id})

    candidate_cases = {item.case.id: item for item in candidate.cases}
    if len(candidate_cases) != len(candidate.cases) or len(candidate_cases) != len(baseline.cases):
        raise RunComparisonError("Evaluation runs do not contain the same case membership.")

    baseline_ids = {item.case.id for item in baseline.cases}
    if len(baseline_ids) != len(baseline.cases):
        raise RunComparisonError("Baseline run contains duplicate case membership.")

    rows: list[RunComparisonRow] = []
    for baseline_item in sorted(baseline.cases, key=lambda item: item.case.ordinal):
        candidate_item = candidate_cases.get(baseline_item.case.id)
        if candidate_item is None:
            raise RunComparisonError("Evaluation runs do not contain the same case membership.")
        if candidate_item.case != baseline_item.case:
            raise RunComparisonError("Evaluation runs contain different records for the same case.")
        if not _case_matches_scope(baseline_item.case, comparison_scope):
            continue

        baseline_attempt = baseline_item.attempt
        candidate_attempt = candidate_item.attempt
        duration_delta_ms = (
            None
            if baseline_attempt.duration_ms is None or candidate_attempt.duration_ms is None
            else candidate_attempt.duration_ms - baseline_attempt.duration_ms
        )
        rows.append(
            RunComparisonRow(
                case=baseline_item.case,
                baseline_attempt=baseline_attempt,
                candidate_attempt=candidate_attempt,
                transition=_transition(baseline_attempt, candidate_attempt),
                duration_delta_ms=duration_delta_ms,
            )
        )

    transition_counts = {
        transition: sum(row.transition is transition for row in rows) for transition in RunComparisonTransition
    }
    return RunComparison(
        dataset=baseline.dataset,
        scope=comparison_scope,
        baseline_run=baseline.run,
        candidate_run=candidate.run,
        baseline_summary=_summary([row.baseline_attempt for row in rows]),
        candidate_summary=_summary([row.candidate_attempt for row in rows]),
        transition_counts=RunComparisonTransitionCounts(
            improved=transition_counts[RunComparisonTransition.IMPROVED],
            regressed=transition_counts[RunComparisonTransition.REGRESSED],
            newly_errored=transition_counts[RunComparisonTransition.NEWLY_ERRORED],
            recovered=transition_counts[RunComparisonTransition.RECOVERED],
            unchanged=transition_counts[RunComparisonTransition.UNCHANGED],
            changed=transition_counts[RunComparisonTransition.CHANGED],
        ),
        rows=tuple(rows),
    )
