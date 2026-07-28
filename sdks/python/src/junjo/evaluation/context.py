"""Immutable evaluation context and bounded OpenTelemetry role spans."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import StrEnum

from opentelemetry import trace
from opentelemetry.trace import Span

from ..telemetry.otel_schema import (
    JUNJO_OTEL_MODULE_NAME,
    JUNJO_TELEMETRY_CONTRACT_VERSION,
)
from ..telemetry.span_lifecycle import (
    mark_span_cancelled,
    mark_span_failed,
    record_span_exception,
)

EVALUATION_CONTEXT_VERSION = 1
_SOURCE_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class EvaluationRunClass(StrEnum):
    """Classification of explicit evaluation-system execution."""

    DATASET_GENERATION = "dataset_generation"
    EVALUATION = "evaluation"


class EvaluationRole(StrEnum):
    """The bounded role represented by one Junjo-owned evaluation span."""

    ORCHESTRATOR = "orchestrator"
    SUBJECT = "subject"
    JUDGE = "judge"
    VERIFIER = "verifier"


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """Immutable identities for one evaluation or generated-case execution.

    Ordinary application execution does not need an ``EvaluationContext``.
    Its absence is the compact representation of normal application traffic.

    :param run_class: Evaluation or dataset-generation classification.
    :param dataset_id: Canonical Studio Dataset ID.
    :param source_revision: Clean committed application source revision.
    :param role: Role of the span or callback receiving this context.
    :param run_id: Canonical Studio Run ID for an evaluation Attempt.
    :param case_id: Canonical Studio Case ID for an evaluation Attempt.
    :param case_key: Requested Case key before a generated Case exists.
    :param attempt_id: Canonical Studio Attempt ID for an evaluation Attempt.
    """

    run_class: EvaluationRunClass
    dataset_id: str
    source_revision: str
    role: EvaluationRole = EvaluationRole.ORCHESTRATOR
    run_id: str | None = None
    case_id: str | None = None
    case_key: str | None = None
    attempt_id: str | None = None
    version: int = EVALUATION_CONTEXT_VERSION

    def __post_init__(self) -> None:
        if self.version != EVALUATION_CONTEXT_VERSION:
            raise ValueError(f"Evaluation context version must be {EVALUATION_CONTEXT_VERSION}.")
        if not isinstance(self.run_class, EvaluationRunClass):
            raise TypeError("Evaluation run_class must be EvaluationRunClass.")
        if not isinstance(self.role, EvaluationRole):
            raise TypeError("Evaluation role must be EvaluationRole.")
        _validate_identity("dataset_id", self.dataset_id)
        for name, value in (
            ("run_id", self.run_id),
            ("case_id", self.case_id),
            ("case_key", self.case_key),
            ("attempt_id", self.attempt_id),
        ):
            _validate_optional_identity(name, value)
        if not isinstance(self.source_revision, str) or _SOURCE_REVISION.fullmatch(self.source_revision) is None:
            raise ValueError("Evaluation source_revision must be 40 or 64 lowercase hexadecimal characters.")
        if self.run_class is EvaluationRunClass.EVALUATION:
            if self.run_id is None or self.case_id is None or self.attempt_id is None or self.case_key is not None:
                raise ValueError(
                    "Evaluation context requires run_id, case_id, and attempt_id, and cannot use case_key."
                )
        elif (
            self.case_key is None or self.run_id is not None or self.case_id is not None or self.attempt_id is not None
        ):
            raise ValueError(
                "Dataset-generation context requires case_key and cannot contain Run, Case, or Attempt IDs."
            )

    def for_role(self, role: EvaluationRole) -> EvaluationContext:
        """Return a copy for one subject, judge, or verifier boundary."""

        return replace(self, role=role)

    def attributes(self) -> dict[str, str | int]:
        """Return the exact bounded attributes governed by ADR 0014."""

        attributes: dict[str, str | int] = {
            "junjo.evaluation.context.version": self.version,
            "junjo.evaluation.run_class": self.run_class.value,
            "junjo.evaluation.role": self.role.value,
            "junjo.telemetry.contract_version": JUNJO_TELEMETRY_CONTRACT_VERSION,
        }
        optional_attributes = (
            ("junjo.evaluation.dataset.id", self.dataset_id),
            ("junjo.evaluation.run.id", self.run_id),
            ("junjo.evaluation.case.id", self.case_id),
            ("junjo.evaluation.case.key", self.case_key),
            ("junjo.evaluation.attempt.id", self.attempt_id),
            ("junjo.evaluation.source.revision", self.source_revision),
        )
        for name, value in optional_attributes:
            if value is not None:
                attributes[name] = value
        return attributes


@contextmanager
def evaluation_span(context: EvaluationContext) -> Iterator[Span]:
    """Start one bounded Junjo-owned evaluation role span.

    This function does not alter the active OpenTelemetry Resource, so the
    application's configured service identity remains authoritative.
    """

    name = _span_name(context)
    tracer = trace.get_tracer(JUNJO_OTEL_MODULE_NAME)
    with tracer.start_as_current_span(
        name,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        for key, value in context.attributes().items():
            span.set_attribute(key, value)
        try:
            yield span
        except asyncio.CancelledError as error:
            mark_span_cancelled(span, error)
            raise
        except Exception as error:
            mark_evaluation_span_failed(span, error)
            raise


def mark_evaluation_span_failed(span: Span, error: BaseException) -> None:
    """Mark a handled evaluation failure using Junjo's standard diagnostics."""

    mark_span_failed(span, error)
    record_span_exception(span, error)


def _span_name(context: EvaluationContext) -> str:
    if context.role is EvaluationRole.SUBJECT:
        return "junjo.evaluation.subject"
    if context.role is EvaluationRole.JUDGE:
        return "junjo.evaluation.judge"
    if context.role is EvaluationRole.VERIFIER:
        return "junjo.evaluation.verifier"
    if context.run_class is EvaluationRunClass.EVALUATION:
        return "junjo.evaluation.attempt"
    if context.run_class is EvaluationRunClass.DATASET_GENERATION:
        return "junjo.evaluation.dataset_generation"
    raise ValueError("Ordinary application execution is represented by the absence of an evaluation span.")


def _validate_optional_identity(name: str, value: str | None) -> None:
    if value is None:
        return
    _validate_identity(name, value)


def _validate_identity(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(f"Evaluation {name} must be a non-empty string of at most 256 characters.")
