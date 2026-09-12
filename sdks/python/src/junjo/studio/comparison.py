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
    """Number of selected cases on this side of the comparison, including errors and queued attempts."""
    judged: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Attempts judged passed or failed; excludes queued attempts and operational errors."""
    passed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Attempts satisfying the evaluator criteria."""
    failed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Attempts that did not satisfy the evaluator criteria."""
    error: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Attempts whose target or evaluator could not complete successfully."""
    queued: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Attempts that have not received a terminal result."""
    pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    """Passed divided by judged attempts, as a fraction from 0 to 1; None when nothing was judged."""


class RunComparisonTransitionCounts(StudioDto):
    """Counts for every supported transition category."""

    improved: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Cases whose status changed from failed in the baseline to passed in the candidate."""
    regressed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Cases whose status changed from passed in the baseline to failed in the candidate."""
    newly_errored: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Cases with a candidate operational error whose baseline was not an error."""
    recovered: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Cases whose baseline errored and whose candidate no longer errors; inspect whether it passed or failed."""
    unchanged: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Cases with the same attempt status on both sides; output or timing may still differ."""
    changed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Other status transitions not classified as improved, regressed, newly errored, recovered, or unchanged."""


class RunComparisonRow(StudioDto):
    """One exact dataset case aligned across baseline and candidate runs."""

    case: CaseRead
    """The stored case, including input, evaluation criteria, and provenance."""
    baseline_attempt: AttemptRead
    """The baseline attempt for this exact immutable case."""
    candidate_attempt: AttemptRead
    """The candidate attempt for the same immutable case."""
    transition: RunComparisonTransition
    """Deterministic outcome classification comparing candidate status with baseline status."""
    duration_delta_ms: int | None
    """Candidate subject duration minus baseline duration in milliseconds; None if either duration is missing."""


class RunComparison(StudioDto):
    """Comparison of two revisions evaluated against one locked dataset.

    Use the aligned case outcomes before requesting larger trace payloads.
    An unchanged status does not mean the output or execution was identical.

    .. code-block:: python

        comparison = await studio.compare_runs(baseline_id, candidate_id)
        for row in comparison.rows:
            print(row.case.case_key, row.transition, row.duration_delta_ms)
        print(comparison.transition_counts.regressed)
        print(comparison.transition_counts.newly_errored)
    """

    dataset: DatasetRead
    """Dataset metadata, including its immutable identity and lock status."""
    scope: RunScope
    """Conjunctive case filters used to select the comparison rows."""
    baseline_run: RunRead
    """Baseline run metadata and its clean committed application revision."""
    candidate_run: RunRead
    """Candidate run metadata and its clean committed application revision."""
    baseline_summary: RunComparisonSummary
    """Outcome totals for the baseline cases selected by the comparison scope."""
    candidate_summary: RunComparisonSummary
    """Outcome totals for the candidate cases selected by the comparison scope."""
    transition_counts: RunComparisonTransitionCounts
    """Counts of status transitions across the aligned cases."""
    rows: tuple[RunComparisonRow, ...] = Field(max_length=MAX_CASES_PER_DATASET)
    """Comparison rows aligned by immutable case identity and ordered by dataset ordinal."""


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
