"""Sequential ordering, recovery, resource, binding, and generation behavior."""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from pydantic import JsonValue

from junjo.evaluation import (
    CaseGenerationError,
    DirtySourceTreeError,
    EvaluationContext,
    EvaluationExecutor,
    EvaluationHarness,
    EvaluationResult,
    EvaluationRole,
    EvaluationRunError,
    EvaluationTarget,
    Evaluator,
    ExecutionServiceIdentity,
    GenerateCaseRequest,
    HarnessConfigurationError,
    TargetContractError,
    TargetExecution,
    TargetExecutionError,
    clean_source_revision,
)
from junjo.studio import (
    AttemptRead,
    AttemptResultWrite,
    AttemptStatus,
    CaseCreate,
    CaseOrigin,
    CaseRead,
    DatasetDetail,
    DatasetRead,
    DatasetStatus,
    ExecutableType,
    RunCaseRead,
    RunDetail,
    RunRead,
    RunStart,
    RunStatus,
    SemanticExecutionReference,
    TargetKind,
)

NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)
REVISION = "c" * 40


def _dataset(
    status: DatasetStatus = DatasetStatus.LOCKED,
    *,
    application_key: str = "example",
) -> DatasetRead:
    return DatasetRead(
        id="dataset-1",
        key="places",
        application_key=application_key,
        name="Places",
        description=None,
        status=status,
        created_by_user_id="user-1",
        created_at=NOW,
        locked_at=NOW if status is DatasetStatus.LOCKED else None,
    )


def _case(
    key: str,
    ordinal: int,
    *,
    message: str | None = None,
    origin: CaseOrigin = CaseOrigin.AUTHORED,
    source_execution: SemanticExecutionReference | None = None,
    source_revision: str | None = None,
) -> CaseRead:
    return CaseRead(
        id=f"case-{key}",
        dataset_id="dataset-1",
        case_key=key,
        evaluation_name="Fake exact match",
        ordinal=ordinal,
        origin=origin,
        target_kind=TargetKind.NODE,
        target_key="fake",
        target_name="Fake Node",
        input_version=1,
        input_json={"message": message or key},
        expectation_json={"expected": "pass"},
        evaluator_key="fake-evaluator",
        evaluator_version=1,
        source_execution=source_execution,
        source_revision=source_revision,
        created_at=NOW,
    )


def _execution(runtime_id: str) -> SemanticExecutionReference:
    return SemanticExecutionReference(
        service_namespace="example.apps",
        service_name="chat",
        executable_type=ExecutableType.WORKFLOW,
        runtime_id=runtime_id,
    )


def _attempt(
    case: CaseRead,
    *,
    status: AttemptStatus = AttemptStatus.QUEUED,
    execution: SemanticExecutionReference | None = None,
) -> AttemptRead:
    terminal = status is not AttemptStatus.QUEUED
    return AttemptRead(
        id=f"attempt-{case.case_key}",
        run_id="run-1",
        case_id=case.id,
        status=status,
        reason="already passed" if status is AttemptStatus.PASSED else None,
        duration_ms=1 if terminal else None,
        subject_execution=execution,
        execution_bound_at=NOW if execution is not None else None,
        recorded_at=NOW if terminal else None,
    )


def _run_detail(
    memberships: list[RunCaseRead],
    *,
    dataset: DatasetRead | None = None,
    source_revision: str = REVISION,
) -> RunDetail:
    selected_dataset = dataset or _dataset()
    return RunDetail(
        run=RunRead(
            id="run-1",
            dataset_id=selected_dataset.id,
            request_key="baseline-1",
            run_label="baseline",
            source_revision=source_revision,
            status=RunStatus.ACTIVE,
            created_by_user_id="user-1",
            created_at=NOW,
            completed_at=None,
        ),
        dataset=selected_dataset,
        cases=tuple(memberships),
    )


class FakeClient:
    def __init__(self, detail: RunDetail, events: list[str]) -> None:
        self.detail = detail
        self.events = events
        self.results: dict[str, AttemptResultWrite] = {}
        self.added_case: CaseCreate | None = None

    async def get_dataset(self, dataset_id: str) -> DatasetDetail:
        assert dataset_id == self.detail.dataset.id
        return DatasetDetail(
            dataset=self.detail.dataset,
            cases=tuple(item.case for item in self.detail.cases),
        )

    async def start_run(self, request: RunStart) -> RunDetail:
        self.events.append("start")
        assert request.source_revision == REVISION
        return self.detail

    async def get_run(self, run_id: str) -> RunDetail:
        assert run_id == self.detail.run.id
        self.events.append("get-run")
        return self.detail

    async def bind_attempt_execution(
        self,
        attempt_id: str,
        execution: SemanticExecutionReference,
    ) -> AttemptRead:
        self.events.append(f"bind:{attempt_id}:{execution.runtime_id}")
        membership = next(item for item in self.detail.cases if item.attempt.id == attempt_id)
        return membership.attempt.model_copy(
            update={
                "subject_execution": execution,
                "execution_bound_at": NOW,
            }
        )

    async def record_attempt_result(
        self,
        attempt_id: str,
        result: AttemptResultWrite,
    ) -> AttemptRead:
        self.events.append(f"result:{attempt_id}:{result.status.value}")
        self.results[attempt_id] = result
        membership = next(item for item in self.detail.cases if item.attempt.id == attempt_id)
        return membership.attempt.model_copy(
            update={
                "status": result.status,
                "reason": result.reason,
                "duration_ms": result.duration_ms,
                "recorded_at": NOW,
            }
        )

    async def add_case(
        self,
        dataset_id: str,
        request: CaseCreate,
    ) -> CaseRead:
        assert dataset_id == self.detail.dataset.id
        self.events.append(f"add-case:{request.case_key}")
        self.added_case = request
        input_json = cast(Mapping[str, JsonValue], request.input_json)
        return _case(
            request.case_key,
            1,
            message=str(input_json["message"]),
            origin=request.origin,
            source_execution=request.source_execution,
            source_revision=request.source_revision,
        )


class FakeTarget(EvaluationTarget):
    kind = TargetKind.NODE
    key = "fake"
    name = "Fake Node"
    input_version = 1

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.resources: list[object] = []

    @property
    def input_schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "required": ["message"],
        }

    def validate_input(self, input_json: object) -> object:
        if not isinstance(input_json, dict):
            raise TargetContractError("message is required")
        values = cast(dict[str, object], input_json)
        if not isinstance(values.get("message"), str):
            raise TargetContractError("message is required")
        if values["message"] == "invalid":
            raise TargetContractError("invalid case")
        return values["message"]

    async def execute(
        self,
        input_value: object,
        *,
        context: EvaluationContext,
        service_identity: ExecutionServiceIdentity,
        resources: object,
    ) -> TargetExecution:
        assert context.role is EvaluationRole.SUBJECT
        message = str(input_value)
        self.events.append(f"target:{message}")
        self.resources.append(resources)
        execution = service_identity.reference(
            executable_type=ExecutableType.WORKFLOW,
            runtime_id=f"runtime-{message}",
        )
        if message == "target-error":
            raise TargetExecutionError(
                "Target failed safely.",
                execution=execution,
                duration_ms=9,
            )
        return TargetExecution(
            subject=f"subject:{message}",
            execution=execution,
            duration_ms=7,
        )


class FakeEvaluator(Evaluator):
    key = "fake-evaluator"
    version = 1
    role = EvaluationRole.JUDGE
    timeout_seconds = 30.0

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.resources: list[object] = []

    @property
    def expectation_schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {"expected": {"const": "pass"}},
            "required": ["expected"],
            "additionalProperties": False,
        }

    def validate_expectation(
        self,
        expectation_json: JsonValue | None,
    ) -> object:
        if expectation_json != {"expected": "pass"}:
            raise ValueError("invalid expectation")
        return expectation_json

    async def evaluate(
        self,
        *,
        subject: object,
        expectation: object,
        context: EvaluationContext,
        resources: object,
    ) -> EvaluationResult:
        del expectation
        assert context.role is EvaluationRole.JUDGE
        self.resources.append(resources)
        self.events.append(f"judge:{subject}")
        if subject == "subject:evaluator-error":
            await asyncio.sleep(0.02)
        return EvaluationResult(
            passed=True,
            reason="Evaluation passed.",
        )


def _harness(
    events: list[str],
) -> tuple[EvaluationHarness[object], FakeTarget, FakeEvaluator]:
    target = FakeTarget(events)
    evaluator = FakeEvaluator(events)
    shared_resources = object()

    @asynccontextmanager
    async def resources() -> AsyncIterator[object]:
        events.append("resources:enter")
        try:
            yield shared_resources
        finally:
            events.append("resources:exit")

    return (
        EvaluationHarness(
            application_key="example",
            service_identity=ExecutionServiceIdentity(
                service_namespace="example.apps",
                service_name="chat",
            ),
            targets=(target,),
            evaluators=(evaluator,),
            runtime_context=resources,
        ),
        target,
        evaluator,
    )


def test_harness_rejects_duplicate_and_unknown_registration_contracts() -> None:
    events: list[str] = []
    harness, target, evaluator = _harness(events)

    @asynccontextmanager
    async def resources() -> AsyncIterator[object]:
        yield object()

    with pytest.raises(ValueError, match="Duplicate target"):
        EvaluationHarness(
            application_key="example",
            service_identity=harness.service_identity,
            targets=(target, target),
            evaluators=(evaluator,),
            runtime_context=resources,
        )

    unknown = _case("unknown", 1).model_copy(update={"target_key": "missing"})
    with pytest.raises(LookupError, match="Unknown target"):
        harness.prepare_case(unknown)
    renamed = _case("renamed", 2).model_copy(update={"target_name": "Different Node"})
    with pytest.raises(HarnessConfigurationError, match="does not match"):
        harness.prepare_case(renamed)
    assert events == []


@pytest.mark.asyncio
async def test_runner_orders_cases_reuses_resources_and_continues_after_errors() -> None:
    events: list[str] = []
    terminal = _case("terminal", 1)
    bound = _case("bound", 2)
    target_error = _case("target-error", 3)
    evaluator_error = _case("evaluator-error", 4)
    good = _case("good", 5)
    invalid = _case("invalid", 6)
    detail = _run_detail(
        [
            RunCaseRead(case=invalid, attempt=_attempt(invalid)),
            RunCaseRead(case=good, attempt=_attempt(good)),
            RunCaseRead(
                case=terminal,
                attempt=_attempt(terminal, status=AttemptStatus.PASSED),
            ),
            RunCaseRead(
                case=bound,
                attempt=_attempt(bound, execution=_execution("prior-runtime")),
            ),
            RunCaseRead(
                case=target_error,
                attempt=_attempt(target_error),
            ),
            RunCaseRead(
                case=evaluator_error,
                attempt=_attempt(evaluator_error),
            ),
        ]
    )
    client = FakeClient(detail, events)
    harness, target, evaluator = _harness(events)
    evaluator.timeout_seconds = 0.001
    assert harness.target_descriptors()[0].key == "fake"
    evaluator_descriptor = harness.evaluator_descriptors()[0]
    assert evaluator_descriptor.key == "fake-evaluator"
    assert evaluator_descriptor.role is EvaluationRole.JUDGE
    assert evaluator_descriptor.expectation_schema["additionalProperties"] is False
    assert events == []

    async with EvaluationExecutor(
        client=client,
        harness=harness,
        source_revision=lambda: REVISION,
    ) as executor:
        result = await executor.run(
            dataset_id="dataset-1",
            request_key="baseline-1",
            run_label="baseline",
        )

    assert result.run.id == "run-1"
    assert events == [
        "start",
        "result:attempt-bound:error",
        "resources:enter",
        "target:target-error",
        "bind:attempt-target-error:runtime-target-error",
        "result:attempt-target-error:error",
        "target:evaluator-error",
        "bind:attempt-evaluator-error:runtime-evaluator-error",
        "judge:subject:evaluator-error",
        "result:attempt-evaluator-error:error",
        "target:good",
        "bind:attempt-good:runtime-good",
        "judge:subject:good",
        "result:attempt-good:passed",
        "result:attempt-invalid:error",
        "get-run",
        "resources:exit",
    ]
    assert len(target.resources) == 3
    assert len({id(resource) for resource in target.resources}) == 1
    assert evaluator.resources == [
        target.resources[0],
        target.resources[0],
    ]
    assert "attempt-terminal" not in client.results
    assert client.results["attempt-bound"].status is AttemptStatus.ERROR


@pytest.mark.asyncio
async def test_executor_skips_runtime_when_no_target_can_execute() -> None:
    events: list[str] = []
    terminal = _case("terminal", 1)
    bound = _case("bound", 2)
    invalid = _case("invalid", 3).model_copy(update={"target_key": "missing"})
    detail = _run_detail(
        [
            RunCaseRead(
                case=terminal,
                attempt=_attempt(terminal, status=AttemptStatus.PASSED),
            ),
            RunCaseRead(
                case=bound,
                attempt=_attempt(bound, execution=_execution("prior-runtime")),
            ),
            RunCaseRead(case=invalid, attempt=_attempt(invalid)),
        ]
    )
    client = FakeClient(detail, events)
    harness, target, evaluator = _harness(events)

    async with EvaluationExecutor(
        client=client,
        harness=harness,
        source_revision=lambda: REVISION,
    ) as executor:
        await executor.resume(run_id="run-1")

    assert events == [
        "get-run",
        "result:attempt-bound:error",
        "result:attempt-invalid:error",
        "get-run",
    ]
    assert target.resources == []
    assert evaluator.resources == []


@pytest.mark.asyncio
async def test_executor_reuses_one_runtime_across_multiple_runs() -> None:
    events: list[str] = []
    case = _case("good", 1)
    detail = _run_detail([RunCaseRead(case=case, attempt=_attempt(case))])
    client = FakeClient(detail, events)
    harness, target, evaluator = _harness(events)

    async with EvaluationExecutor(
        client=client,
        harness=harness,
        source_revision=lambda: REVISION,
    ) as executor:
        await executor.run(
            dataset_id="dataset-1",
            request_key="baseline-1",
            run_label="baseline",
        )
        await executor.run(
            dataset_id="dataset-1",
            request_key="candidate-1",
            run_label="candidate",
        )

    assert events.count("resources:enter") == 1
    assert events.count("resources:exit") == 1
    assert len(target.resources) == 2
    assert target.resources[0] is target.resources[1]
    assert evaluator.resources == target.resources


@pytest.mark.asyncio
async def test_executor_requires_an_explicit_async_lifetime() -> None:
    events: list[str] = []
    case = _case("good", 1)
    detail = _run_detail([RunCaseRead(case=case, attempt=_attempt(case))])
    harness, _target, _evaluator = _harness(events)
    executor = EvaluationExecutor(
        client=FakeClient(detail, events),
        harness=harness,
        source_revision=lambda: REVISION,
    )

    with pytest.raises(RuntimeError, match="async context manager"):
        await executor.resume(run_id="run-1")

    assert events == []


@pytest.mark.asyncio
async def test_result_write_failure_stops_and_bound_resume_never_reexecutes() -> None:
    events: list[str] = []
    case = _case("write", 1)
    detail = _run_detail([RunCaseRead(case=case, attempt=_attempt(case))])

    class FailingResultClient(FakeClient):
        async def record_attempt_result(
            self,
            attempt_id: str,
            result: AttemptResultWrite,
        ) -> AttemptRead:
            self.events.append(f"result-failed:{attempt_id}:{result.status.value}")
            raise ConnectionError("result transport failed")

    harness, target, _evaluator = _harness(events)
    with pytest.raises(ConnectionError, match="result transport"):
        async with EvaluationExecutor(
            client=FailingResultClient(detail, events),
            harness=harness,
            source_revision=lambda: REVISION,
        ) as executor:
            await executor.run(
                dataset_id="dataset-1",
                request_key="baseline-1",
                run_label="baseline",
            )
    assert len(target.resources) == 1

    resumed_detail = _run_detail(
        [
            RunCaseRead(
                case=case,
                attempt=_attempt(
                    case,
                    execution=_execution("runtime-write"),
                ),
            )
        ]
    )
    resume_client = FakeClient(resumed_detail, events)
    async with EvaluationExecutor(
        client=resume_client,
        harness=harness,
        source_revision=lambda: REVISION,
    ) as executor:
        await executor.resume(run_id="run-1")

    assert len(target.resources) == 1
    assert resume_client.results["attempt-write"].status is AttemptStatus.ERROR


@pytest.mark.asyncio
async def test_resume_rejects_a_different_clean_source_revision() -> None:
    events: list[str] = []
    case = _case("one", 1)
    detail = _run_detail([RunCaseRead(case=case, attempt=_attempt(case))])
    harness, _target, _evaluator = _harness(events)

    with pytest.raises(EvaluationRunError, match="does not match"):
        async with EvaluationExecutor(
            client=FakeClient(detail, events),
            harness=harness,
            source_revision=lambda: "d" * 40,
        ) as executor:
            await executor.resume(run_id="run-1")

    assert events == ["get-run"]


@pytest.mark.asyncio
async def test_generation_retains_curated_contract_and_source_execution() -> None:
    events: list[str] = []
    placeholder = _case("placeholder", 1)
    detail = _run_detail(
        [RunCaseRead(case=placeholder, attempt=_attempt(placeholder))],
        dataset=_dataset(DatasetStatus.DRAFT),
    )
    client = FakeClient(detail, events)
    harness, target, evaluator = _harness(events)

    async with EvaluationExecutor(
        client=client,
        harness=harness,
        source_revision=lambda: REVISION,
    ) as executor:
        result = await executor.generate_case(
            GenerateCaseRequest(
                dataset_id="dataset-1",
                case_key="generated",
                evaluation_name="Fake exact match",
                target_kind=TargetKind.NODE,
                target_key="fake",
                input_version=1,
                input_json={"message": "generated-message"},
                expectation_json={"expected": "pass"},
                evaluator_key="fake-evaluator",
                evaluator_version=1,
            )
        )

    assert result.case_key == "generated"
    assert client.added_case is not None
    assert client.added_case.origin is CaseOrigin.GENERATED
    assert client.added_case.expectation_json == {"expected": "pass"}
    assert client.added_case.expectation_json != {"subject": "subject:generated-message"}
    assert client.added_case.source_revision == REVISION
    assert client.added_case.source_execution is not None
    assert client.added_case.source_execution.runtime_id == "runtime-generated-message"
    assert len(target.resources) == 1
    assert evaluator.resources == []
    assert events == [
        "resources:enter",
        "target:generated-message",
        "add-case:generated",
        "resources:exit",
    ]


@pytest.mark.asyncio
async def test_generation_retry_and_conflict_fail_before_execution() -> None:
    events: list[str] = []
    existing = _case(
        "generated",
        1,
        message="generated-message",
        origin=CaseOrigin.GENERATED,
        source_execution=_execution("source-runtime"),
        source_revision=REVISION,
    )
    detail = _run_detail(
        [RunCaseRead(case=existing, attempt=_attempt(existing))],
        dataset=_dataset(DatasetStatus.DRAFT),
    )
    client = FakeClient(detail, events)
    harness, target, _evaluator = _harness(events)
    request = GenerateCaseRequest(
        dataset_id="dataset-1",
        case_key="generated",
        evaluation_name="Fake exact match",
        target_kind=TargetKind.NODE,
        target_key="fake",
        input_version=1,
        input_json={"message": "generated-message"},
        expectation_json={"expected": "pass"},
        evaluator_key="fake-evaluator",
        evaluator_version=1,
    )

    async with EvaluationExecutor(
        client=client,
        harness=harness,
        source_revision=lambda: REVISION,
    ) as executor:
        assert await executor.generate_case(request) == existing
    assert target.resources == []
    assert events == []

    with pytest.raises(CaseGenerationError, match="different generated content"):
        async with EvaluationExecutor(
            client=client,
            harness=harness,
            source_revision=lambda: REVISION,
        ) as executor:
            await executor.generate_case(
                GenerateCaseRequest(
                    dataset_id=request.dataset_id,
                    case_key=request.case_key,
                    evaluation_name=request.evaluation_name,
                    target_kind=request.target_kind,
                    target_key=request.target_key,
                    input_version=request.input_version,
                    input_json={"message": "changed"},
                    expectation_json=request.expectation_json,
                    evaluator_key=request.evaluator_key,
                    evaluator_version=request.evaluator_version,
                )
            )
    assert target.resources == []
    assert events == []


def test_clean_source_revision_requires_a_clean_committed_worktree(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Junjo Test"],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "config",
            "user.email",
            "test@junjo.example",
        ],
        check=True,
    )
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("clean\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "tracked.txt"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-qm", "initial"],
        check=True,
    )
    expected = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert clean_source_revision(tracked) == expected
    (tmp_path / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(DirtySourceTreeError, match="clean committed"):
        clean_source_revision(tmp_path)
