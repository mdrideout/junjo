"""Sequential, resume-safe Studio evaluation coordination."""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol

from pydantic import JsonValue

from ..studio import (
    TERMINAL_ATTEMPT_STATUSES,
    AttemptRead,
    AttemptResultWrite,
    AttemptStatus,
    CaseCreate,
    CaseOrigin,
    CaseRead,
    DatasetDetail,
    DatasetStatus,
    RunDetail,
    RunStart,
    SemanticExecutionReference,
    TargetKind,
)
from .context import (
    EvaluationContext,
    EvaluationRole,
    EvaluationRunClass,
    evaluation_span,
    mark_evaluation_span_failed,
)
from .harness import EvaluationHarness
from .provenance import SourceRevision, clean_source_revision
from .targets import TargetExecutionError

INTERRUPTED_REASON = (
    "The previous runner stopped after binding execution evidence but before "
    "recording a judgment. Start a new run to execute this case again."
)


class EvaluationControlClient(Protocol):
    """Studio operations required by the sequential runner."""

    async def get_dataset(self, dataset_id: str) -> DatasetDetail: ...

    async def start_run(self, request: RunStart) -> RunDetail: ...

    async def get_run(self, run_id: str) -> RunDetail: ...

    async def bind_attempt_execution(
        self,
        attempt_id: str,
        execution: SemanticExecutionReference,
    ) -> AttemptRead: ...

    async def record_attempt_result(
        self,
        attempt_id: str,
        result: AttemptResultWrite,
    ) -> AttemptRead: ...

    async def add_case(self, dataset_id: str, request: CaseCreate) -> CaseRead: ...


class EvaluationRunError(RuntimeError):
    """A run cannot be started or resumed truthfully."""


class CaseGenerationError(RuntimeError):
    """A generated case cannot be executed or recorded truthfully."""


@dataclass(frozen=True, slots=True)
class GenerateCaseRequest:
    """Complete curated contract for one real-execution-generated Case."""

    dataset_id: str
    case_key: str
    evaluation_name: str
    target_kind: TargetKind
    target_key: str
    input_version: int
    input_json: JsonValue
    expectation_json: JsonValue | None
    evaluator_key: str
    evaluator_version: int


_RUNTIME_NOT_ENTERED = object()


class EvaluationExecutor:
    """Run application-owned evaluations inside one explicit host lifetime.

    Enter the executor as an asynchronous context manager. It acquires the
    application's runtime lazily before the first real target execution, reuses
    that runtime across generated cases and Runs, and closes it once on exit.
    Terminal or interrupted Attempts and local contract failures do not start
    application resources.
    """

    def __init__(
        self,
        *,
        client: EvaluationControlClient,
        harness: EvaluationHarness,
        source_revision: SourceRevision | None = None,
    ) -> None:
        self._client = client
        self._harness = harness
        self._source_revision = source_revision or clean_source_revision
        self._exit_stack: AsyncExitStack | None = None
        self._runtime: object = _RUNTIME_NOT_ENTERED

    async def __aenter__(self) -> EvaluationExecutor:
        """Open one reusable evaluation-host lifetime."""

        if self._exit_stack is not None:
            raise RuntimeError("EvaluationExecutor is already open.")
        stack = AsyncExitStack()
        await stack.__aenter__()
        self._exit_stack = stack
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close application runtime resources acquired by this executor."""

        stack = self._require_open()
        self._exit_stack = None
        self._runtime = _RUNTIME_NOT_ENTERED
        await stack.__aexit__(exc_type, exc, traceback)

    async def run(
        self,
        *,
        dataset_id: str,
        request_key: str,
        run_label: str,
    ) -> RunDetail:
        """Start or idempotently resume one run at the clean current revision."""

        self._require_open()
        revision = self._source_revision()
        dataset = await self._client.get_dataset(dataset_id)
        self._require_application(dataset.dataset.application_key, dataset_id)
        detail = await self._client.start_run(
            RunStart(
                dataset_id=dataset_id,
                request_key=request_key,
                run_label=run_label,
                source_revision=revision,
            )
        )
        if detail.run.source_revision != revision:
            raise EvaluationRunError("Studio returned an existing run for a different source revision.")
        return await self._process_run(detail)

    async def resume(self, *, run_id: str) -> RunDetail:
        """Resume one existing run only from its exact clean source revision."""

        self._require_open()
        revision = self._source_revision()
        detail = await self._client.get_run(run_id)
        self._require_application(
            detail.dataset.application_key,
            detail.dataset.id,
        )
        if detail.run.source_revision != revision:
            raise EvaluationRunError("The current clean source revision does not match the Studio run.")
        return await self._process_run(detail)

    async def _process_run(self, detail: RunDetail) -> RunDetail:
        for membership in sorted(
            detail.cases,
            key=lambda item: (item.case.ordinal, item.case.id),
        ):
            await self._process_case(
                detail=detail,
                case=membership.case,
                attempt=membership.attempt,
            )
        return await self._client.get_run(detail.run.id)

    async def _process_case(
        self,
        *,
        detail: RunDetail,
        case: CaseRead,
        attempt: AttemptRead,
    ) -> None:
        if attempt.status in TERMINAL_ATTEMPT_STATUSES:
            return
        if attempt.status is not AttemptStatus.QUEUED:
            raise EvaluationRunError(f"Attempt {attempt.id} has unsupported status {attempt.status}.")
        if attempt.subject_execution is not None:
            await self._record_error(
                attempt_id=attempt.id,
                reason=INTERRUPTED_REASON,
            )
            return

        try:
            prepared = self._harness.prepare_case(case)
        except Exception as error:
            await self._record_error(
                attempt_id=attempt.id,
                reason=_bounded_error("Case contract validation failed", error),
            )
            return

        resources = await self._execution_runtime()
        context = EvaluationContext(
            run_class=EvaluationRunClass.EVALUATION,
            dataset_id=detail.dataset.id,
            run_id=detail.run.id,
            case_id=case.id,
            attempt_id=attempt.id,
            source_revision=detail.run.source_revision,
        )
        with evaluation_span(context) as orchestration_span:
            try:
                with evaluation_span(context.for_role(EvaluationRole.SUBJECT)):
                    target = await self._harness.execute_target(
                        prepared,
                        context=context.for_role(EvaluationRole.SUBJECT),
                        resources=resources,
                    )
            except TargetExecutionError as error:
                if error.execution is not None:
                    await self._client.bind_attempt_execution(
                        attempt.id,
                        error.execution,
                    )
                mark_evaluation_span_failed(orchestration_span, error)
                await self._record_error(
                    attempt_id=attempt.id,
                    reason=str(error),
                    duration_ms=error.duration_ms,
                )
                return
            except Exception as error:
                mark_evaluation_span_failed(orchestration_span, error)
                await self._record_error(
                    attempt_id=attempt.id,
                    reason=_bounded_error("Target execution failed", error),
                )
                return

            await self._client.bind_attempt_execution(
                attempt.id,
                target.execution,
            )
            evaluator_context = context.for_role(prepared.evaluator.role)
            try:
                with evaluation_span(evaluator_context):
                    judgment = await self._harness.evaluate(
                        prepared,
                        subject=target.subject,
                        context=evaluator_context,
                        resources=resources,
                    )
            except Exception as error:
                mark_evaluation_span_failed(orchestration_span, error)
                await self._record_error(
                    attempt_id=attempt.id,
                    reason=_bounded_error("Evaluator failed", error),
                    duration_ms=target.duration_ms,
                )
                return

            await self._client.record_attempt_result(
                attempt.id,
                AttemptResultWrite(
                    status=(AttemptStatus.PASSED if judgment.passed else AttemptStatus.FAILED),
                    reason=judgment.reason,
                    duration_ms=target.duration_ms,
                ),
            )

    async def generate_case(self, request: GenerateCaseRequest) -> CaseRead:
        """Execute one target and retain evidence without blessing its output."""

        self._require_open()
        revision = self._source_revision()
        dataset = await self._client.get_dataset(request.dataset_id)
        if dataset.dataset.application_key != self._harness.application_key:
            raise CaseGenerationError(
                f"Dataset {request.dataset_id} belongs to "
                f"{dataset.dataset.application_key}, not {self._harness.application_key}."
            )
        existing = next(
            (case for case in dataset.cases if case.case_key == request.case_key),
            None,
        )
        if existing is not None:
            if _same_generated_case(
                existing,
                request=request,
                source_revision=revision,
            ):
                return existing
            raise CaseGenerationError(f"Case key {request.case_key} already exists with different generated content.")
        if dataset.dataset.status is not DatasetStatus.DRAFT:
            raise CaseGenerationError("Generated cases can only be added to a draft dataset.")

        try:
            target, input_value, _, _ = self._harness.validate_case_contract(
                target_kind=request.target_kind,
                target_key=request.target_key,
                input_version=request.input_version,
                input_json=request.input_json,
                evaluator_key=request.evaluator_key,
                evaluator_version=request.evaluator_version,
                expectation_json=request.expectation_json,
            )
        except Exception as error:
            raise CaseGenerationError(_bounded_error("Generated case contract validation failed", error)) from error

        context = EvaluationContext(
            run_class=EvaluationRunClass.DATASET_GENERATION,
            dataset_id=request.dataset_id,
            case_key=request.case_key,
            source_revision=revision,
        )
        resources = await self._execution_runtime()
        try:
            with evaluation_span(context):
                with evaluation_span(context.for_role(EvaluationRole.SUBJECT)):
                    result = await self._harness.execute_validated_target(
                        target=target,
                        input_value=input_value,
                        context=context.for_role(EvaluationRole.SUBJECT),
                        resources=resources,
                    )
        except TargetExecutionError as error:
            raise CaseGenerationError(str(error)) from error
        except Exception as error:
            raise CaseGenerationError(_bounded_error("Generated case execution failed", error)) from error

        return await self._client.add_case(
            request.dataset_id,
            CaseCreate(
                case_key=request.case_key,
                evaluation_name=request.evaluation_name,
                origin=CaseOrigin.GENERATED,
                target_kind=request.target_kind,
                target_key=request.target_key,
                target_name=target.name,
                input_version=request.input_version,
                input_json=request.input_json,
                expectation_json=request.expectation_json,
                evaluator_key=request.evaluator_key,
                evaluator_version=request.evaluator_version,
                source_execution=result.execution,
                source_revision=revision,
            ),
        )

    async def _record_error(
        self,
        *,
        attempt_id: str,
        reason: str,
        duration_ms: int | None = None,
    ) -> None:
        await self._client.record_attempt_result(
            attempt_id,
            AttemptResultWrite(
                status=AttemptStatus.ERROR,
                reason=reason[:1_000],
                duration_ms=duration_ms,
            ),
        )

    def _require_application(
        self,
        application_key: str,
        dataset_id: str,
    ) -> None:
        if application_key != self._harness.application_key:
            raise EvaluationRunError(
                f"Dataset {dataset_id} belongs to {application_key}, not {self._harness.application_key}."
            )

    def _require_open(self) -> AsyncExitStack:
        stack = self._exit_stack
        if stack is None:
            raise RuntimeError("EvaluationExecutor must be entered as an async context manager.")
        return stack

    async def _execution_runtime(self) -> object:
        stack = self._require_open()
        if self._runtime is _RUNTIME_NOT_ENTERED:
            self._runtime = await stack.enter_async_context(self._harness.runtime())
        return self._runtime


def _same_generated_case(
    case: CaseRead,
    *,
    request: GenerateCaseRequest,
    source_revision: str,
) -> bool:
    return (
        case.origin is CaseOrigin.GENERATED
        and case.evaluation_name == request.evaluation_name
        and case.target_kind is request.target_kind
        and case.target_key == request.target_key
        and case.input_version == request.input_version
        and case.input_json == request.input_json
        and case.expectation_json == request.expectation_json
        and case.evaluator_key == request.evaluator_key
        and case.evaluator_version == request.evaluator_version
        and case.source_execution is not None
        and case.source_revision == source_revision
    )


def _bounded_error(label: str, error: BaseException) -> str:
    return f"{label}: {type(error).__name__}."[:1_000]
