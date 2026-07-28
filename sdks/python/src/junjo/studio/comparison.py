"""Deterministic baseline/candidate projection over Studio run details."""

from __future__ import annotations

from pydantic import Field

from .errors import RunComparisonError
from .models import (
    MAX_CASES_PER_DATASET,
    AttemptRead,
    CaseRead,
    DatasetRead,
    RunDetail,
    RunRead,
    StudioDto,
)


class RunComparisonRow(StudioDto):
    """One exact dataset case aligned across baseline and candidate runs."""

    case: CaseRead
    baseline_attempt: AttemptRead
    candidate_attempt: AttemptRead
    score_delta: float | None
    duration_delta_ms: int | None


class RunComparison(StudioDto):
    """Comparison of two revisions evaluated against one locked dataset."""

    dataset: DatasetRead
    baseline_run: RunRead
    candidate_run: RunRead
    rows: tuple[RunComparisonRow, ...] = Field(max_length=MAX_CASES_PER_DATASET)


def project_run_comparison(
    baseline: RunDetail,
    candidate: RunDetail,
) -> RunComparison:
    """Align two run details by immutable case identity.

    Score and duration deltas are candidate minus baseline.  Missing terminal
    values remain ``None`` rather than being interpreted as zero.

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

        baseline_attempt = baseline_item.attempt
        candidate_attempt = candidate_item.attempt
        score_delta = (
            None
            if baseline_attempt.score is None or candidate_attempt.score is None
            else candidate_attempt.score - baseline_attempt.score
        )
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
                score_delta=score_delta,
                duration_delta_ms=duration_delta_ms,
            )
        )

    return RunComparison(
        dataset=baseline.dataset,
        baseline_run=baseline.run,
        candidate_run=candidate.run,
        rows=tuple(rows),
    )
