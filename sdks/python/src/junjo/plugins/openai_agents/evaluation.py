"""Evaluation target for an outer OpenAI Agents SDK Agent run."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Generic, Literal, TypeVar, cast, overload

from agents import Agent, RunConfig, Runner, RunResult
from pydantic import TypeAdapter, ValidationError
from typing_extensions import TypeForm

from ...evaluation.context import EvaluationContext
from ...evaluation.targets import (
    Cleanup,
    EvaluationTarget,
    ExecutionServiceIdentity,
    TargetContractError,
    TargetExecution,
    TargetExecutionError,
)
from ...studio import OpenTelemetrySpanReference, TargetKind
from ._instrumentation import _Capture, capture_openai_agent_evidence

InputT = TypeVar("InputT")
ContextT = TypeVar("ContextT")
ResourcesT = TypeVar("ResourcesT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class OpenAIAgentInvocation(Generic[ContextT]):
    """Fresh OpenAI Agent invocation constructed for one evaluation case.

    The application owns Agent construction, input, optional run context and
    configuration, and invocation-scoped cleanup. The evaluation target does
    not replace the application's normal Agent dependencies or model policy.
    """

    agent: Agent[ContextT]
    input: Any
    context: ContextT | None = None
    run_config: RunConfig | None = None
    cleanup: Cleanup | None = None


class OpenAIAgentTarget(EvaluationTarget, Generic[InputT, ContextT, ResourcesT]):
    """Execute an OpenAI Agent and bind its exact standard Agent span.

    The target is conceptual kind ``agent`` in evaluation datasets without
    pretending the external runtime is a native Junjo Agent. It captures the
    one standard ``invoke_agent`` span whose Agent name matches
    ``expected_agent_name`` and returns an exact ``otel_span`` evidence
    reference. Missing, duplicate, or mismatched evidence fails clearly.
    """

    kind = TargetKind.AGENT

    def __init__(
        self,
        *,
        key: str,
        name: str,
        input_version: int,
        input_type: TypeForm[InputT],  # ty: ignore[invalid-type-form]
        expected_agent_name: str,
        factory: Callable[
            [InputT, EvaluationContext, ResourcesT],
            OpenAIAgentInvocation[ContextT] | Awaitable[OpenAIAgentInvocation[ContextT]],
        ],
        projector: Callable[
            [RunResult, InputT, EvaluationContext, ResourcesT],
            object | Awaitable[object],
        ],
    ) -> None:
        """Declare one application-owned outer OpenAI Agent target.

        :param key: Stable dispatch identity within the application harness.
        :param name: Human-readable target name snapshotted into Studio cases.
        :param input_version: Positive version of the target input contract.
        :param input_type: Pydantic-compatible case input type.
        :param expected_agent_name: Exact OpenAI Agent name expected on the
            standard ``invoke_agent`` span.
        :param factory: Application factory for a fresh invocation using the
            validated input, evaluation context, and shared harness resources.
        :param projector: Mapping from the real ``RunResult`` to the subject
            consumed by the case evaluator.
        :raises TargetContractError: If declaration metadata or the input
            contract is invalid.
        """
        _validate_text(key, "target key", 128)
        _validate_text(name, "target name", 256)
        _validate_text(expected_agent_name, "expected Agent name", 256)
        if not isinstance(input_version, int) or isinstance(input_version, bool) or input_version < 1:
            raise TargetContractError("Evaluation target input_version must be a positive integer.")
        self.key = key
        self.name = name
        self.input_version = input_version
        self.expected_agent_name = expected_agent_name
        self._factory = factory
        self._projector = projector
        try:
            self._input_adapter = TypeAdapter(input_type)
            self._input_schema = self._input_adapter.json_schema()
        except Exception as error:
            raise TargetContractError(
                f"Unable to construct the input contract for target {key}:v{input_version}."
            ) from error

    @property
    def input_schema(self) -> dict[str, object]:
        return dict(self._input_schema)

    def validate_input(self, input_json: object) -> InputT:
        try:
            return self._input_adapter.validate_python(input_json)
        except ValidationError as error:
            raise TargetContractError(f"Input does not match target agent:{self.key}:v{self.input_version}.") from error

    async def execute(
        self,
        input_value: object,
        *,
        context: EvaluationContext,
        service_identity: ExecutionServiceIdentity,
        resources: object,
    ) -> TargetExecution:
        del service_identity
        typed_input = cast(InputT, input_value)
        typed_resources = cast(ResourcesT, resources)
        started = perf_counter()
        try:
            invocation = await _resolve(self._factory(typed_input, context, typed_resources))
            if not isinstance(invocation, OpenAIAgentInvocation):
                raise TypeError("OpenAI Agent target factory must return OpenAIAgentInvocation.")
            if invocation.agent.name != self.expected_agent_name:
                raise ValueError("OpenAI Agent invocation name does not match expected_agent_name.")
        except Exception as error:
            raise _target_error("OpenAI Agent target setup failed", error, started=started) from error

        evidence: OpenTelemetrySpanReference | None = None

        async def operation() -> TargetExecution:
            nonlocal evidence
            capture = None
            try:
                with capture_openai_agent_evidence(self.expected_agent_name) as capture:
                    result = await Runner.run(
                        invocation.agent,
                        invocation.input,
                        context=invocation.context,
                        run_config=invocation.run_config,
                    )
            except Exception as error:
                evidence = _single_evidence(capture, required=False)
                raise _target_error(
                    "OpenAI Agent target execution failed",
                    error,
                    started=started,
                    evidence=evidence,
                ) from error

            evidence = _single_evidence(capture, required=True)
            try:
                subject = await _resolve(self._projector(result, typed_input, context, typed_resources))
            except Exception as error:
                raise _target_error(
                    "OpenAI Agent target projection failed",
                    error,
                    started=started,
                    evidence=evidence,
                ) from error
            return TargetExecution(
                subject=subject,
                evidence=evidence,
                duration_ms=_duration_ms(started),
            )

        return await _run_with_cleanup(invocation.cleanup, operation, started=started, evidence=lambda: evidence)


@overload
def _single_evidence(
    capture: _Capture | None,
    *,
    required: Literal[True],
) -> OpenTelemetrySpanReference: ...


@overload
def _single_evidence(
    capture: _Capture | None,
    *,
    required: Literal[False],
) -> OpenTelemetrySpanReference | None: ...


def _single_evidence(
    capture: _Capture | None,
    *,
    required: bool,
) -> OpenTelemetrySpanReference | None:
    values = capture.evidence if capture is not None else []
    if len(values) == 1:
        return values[0]
    if required:
        if not values:
            raise RuntimeError("OpenAI Agent instrumentation did not emit the expected invoke_agent span.")
        raise RuntimeError("OpenAI Agent instrumentation emitted multiple matching Agent spans.")
    return None


async def _run_with_cleanup(
    cleanup: Cleanup | None,
    operation: Callable[[], Awaitable[TargetExecution]],
    *,
    started: float,
    evidence: Callable[[], OpenTelemetrySpanReference | None],
) -> TargetExecution:
    body_error: BaseException | None = None
    try:
        return await operation()
    except BaseException as error:
        body_error = error
        raise
    finally:
        if cleanup is not None:
            try:
                await _resolve(cleanup())
            except Exception as error:
                if body_error is None:
                    raise _target_error(
                        "OpenAI Agent target cleanup failed",
                        error,
                        started=started,
                        evidence=evidence(),
                    ) from error


async def _resolve(value: ResultT | Awaitable[ResultT]) -> ResultT:
    if inspect.isawaitable(value):
        return await cast(Awaitable[ResultT], value)
    return value


def _target_error(
    label: str,
    error: BaseException,
    *,
    started: float,
    evidence: OpenTelemetrySpanReference | None = None,
) -> TargetExecutionError:
    return TargetExecutionError(
        f"{label}: {type(error).__name__}.",
        evidence=evidence,
        duration_ms=_duration_ms(started),
    )


def _duration_ms(started: float) -> int:
    return min(86_400_000, max(0, round((perf_counter() - started) * 1_000)))


def _validate_text(value: str, label: str, max_bytes: int) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TargetContractError(f"Evaluation {label} must be non-empty without surrounding whitespace.")
    if len(value.encode("utf-8")) > max_bytes:
        raise TargetContractError(f"Evaluation {label} must be at most {max_bytes} UTF-8 bytes.")


__all__ = ["OpenAIAgentInvocation", "OpenAIAgentTarget"]
