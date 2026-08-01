"""Explicit application target and evaluator registration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic, TypeVar

from pydantic import JsonValue

from ..studio import CaseRead, TargetKind
from .context import EvaluationContext, EvaluationRole
from .evaluators import EvaluationResult, Evaluator
from .targets import (
    EvaluationTarget,
    ExecutionServiceIdentity,
    TargetExecution,
)

ResourcesT = TypeVar("ResourcesT")


class HarnessConfigurationError(ValueError):
    """The application harness declaration is incomplete or ambiguous."""


class TargetNotRegisteredError(LookupError):
    """A Studio case references no exact target declaration."""


class EvaluatorNotRegisteredError(LookupError):
    """A Studio case references no exact evaluator declaration."""


@dataclass(frozen=True, slots=True)
class TargetDescriptor:
    """Inspectable registered target identity and JSON input schema."""

    kind: TargetKind
    key: str
    input_version: int
    input_schema: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class EvaluatorDescriptor:
    """Inspectable evaluator identity, role, and expectation JSON schema."""

    key: str
    version: int
    role: EvaluationRole
    expectation_schema: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PreparedEvaluation:
    """One case after target input and evaluator expectation validation."""

    case: CaseRead
    target: EvaluationTarget
    input_value: object
    evaluator: Evaluator
    expectation: object


class EvaluationHarness(Generic[ResourcesT]):
    """One explicit application declaration consumed by the SDK runner.

    :param application_key: Stable key matching Studio Datasets for this app.
    :param service_identity: The application's real OpenTelemetry service
        namespace and name. Evaluation does not replace this identity.
    :param targets: Explicit Node, Workflow, and Agent declarations.
    :param evaluators: Explicit built-in or application callback evaluators.
    :param runtime_context: Application-owned asynchronous context for
        process-lifetime telemetry, provider clients, and execution resources.
        It is acquired lazily by an evaluation executor.
    """

    def __init__(
        self,
        *,
        application_key: str,
        service_identity: ExecutionServiceIdentity,
        targets: tuple[EvaluationTarget, ...],
        evaluators: tuple[Evaluator, ...],
        runtime_context: Callable[[], AbstractAsyncContextManager[ResourcesT]],
    ) -> None:
        if not isinstance(application_key, str) or not application_key.strip() or len(application_key) > 128:
            raise HarnessConfigurationError("application_key must be a non-empty string of at most 128 characters.")
        if not isinstance(service_identity, ExecutionServiceIdentity):
            raise HarnessConfigurationError("service_identity must be ExecutionServiceIdentity.")
        if not callable(runtime_context):
            raise HarnessConfigurationError("runtime_context must create an application-owned async runtime context.")
        if not targets:
            raise HarnessConfigurationError("EvaluationHarness requires at least one target.")
        if not evaluators:
            raise HarnessConfigurationError("EvaluationHarness requires at least one evaluator.")

        self.application_key = application_key
        self.service_identity = service_identity
        self._runtime_context = runtime_context
        self._targets = MappingProxyType(_target_registry(targets))
        self._evaluators = MappingProxyType(_evaluator_registry(evaluators))

    @asynccontextmanager
    async def runtime(self) -> AsyncIterator[ResourcesT]:
        """Enter one application-owned evaluation-host runtime.

        Target discovery and schema listing never enter this context. An
        :class:`EvaluationExecutor` enters it lazily before the first real
        target execution, reuses the yielded providers, clients, and telemetry
        runtime across operations, and closes it when the executor exits.
        """

        context = self._runtime_context()
        if not isinstance(context, AbstractAsyncContextManager):
            raise HarnessConfigurationError("runtime_context must return an async context manager.")
        async with context as resources:
            yield resources

    def target_descriptors(self) -> tuple[TargetDescriptor, ...]:
        """Return registered targets in deterministic display order."""

        descriptors = [
            TargetDescriptor(
                kind=target.kind,
                key=target.key,
                input_version=target.input_version,
                input_schema=MappingProxyType(target.input_schema),
            )
            for target in self._targets.values()
        ]
        return tuple(
            sorted(
                descriptors,
                key=lambda item: (
                    item.kind.value,
                    item.key,
                    item.input_version,
                ),
            )
        )

    def evaluator_descriptors(self) -> tuple[EvaluatorDescriptor, ...]:
        """Return registered evaluators in deterministic display order."""

        return tuple(
            EvaluatorDescriptor(
                key=evaluator.key,
                version=evaluator.version,
                role=evaluator.role,
                expectation_schema=MappingProxyType(evaluator.expectation_schema),
            )
            for evaluator in sorted(
                self._evaluators.values(),
                key=lambda item: (item.key, item.version),
            )
        )

    def prepare_case(self, case: CaseRead) -> PreparedEvaluation:
        """Resolve and validate one immutable Studio case before provider work."""

        target_identity = (case.target_kind, case.target_key, case.input_version)
        target = self._targets.get(target_identity)
        if target is None:
            raise TargetNotRegisteredError(
                f"Unknown target {case.target_kind.value}:{case.target_key}:v{case.input_version}."
            )
        evaluator_identity = (case.evaluator_key, case.evaluator_version)
        evaluator = self._evaluators.get(evaluator_identity)
        if evaluator is None:
            raise EvaluatorNotRegisteredError(f"Unknown evaluator {case.evaluator_key}:v{case.evaluator_version}.")
        input_value = target.validate_input(case.input_json)
        expectation = evaluator.validate_expectation(case.expectation_json)
        return PreparedEvaluation(
            case=case,
            target=target,
            input_value=input_value,
            evaluator=evaluator,
            expectation=expectation,
        )

    async def execute_target(
        self,
        prepared: PreparedEvaluation,
        *,
        context: EvaluationContext,
        resources: ResourcesT,
    ) -> TargetExecution:
        """Execute the prepared target through its real public lifecycle."""

        return await prepared.target.execute(
            prepared.input_value,
            context=context,
            service_identity=self.service_identity,
            resources=resources,
        )

    async def evaluate(
        self,
        prepared: PreparedEvaluation,
        *,
        subject: object,
        context: EvaluationContext,
        resources: ResourcesT,
    ) -> EvaluationResult:
        """Invoke one evaluator with its declared timeout and typed expectation."""

        async with asyncio.timeout(prepared.evaluator.timeout_seconds):
            result = await prepared.evaluator.evaluate(
                subject=subject,
                expectation=prepared.expectation,
                context=context,
                resources=resources,
            )
        if not isinstance(result, EvaluationResult):
            raise TypeError(
                f"Evaluator {prepared.evaluator.key}:v{prepared.evaluator.version} must return EvaluationResult."
            )
        return result

    def validate_case_contract(
        self,
        *,
        target_kind: TargetKind,
        target_key: str,
        input_version: int,
        input_json: JsonValue,
        evaluator_key: str,
        evaluator_version: int,
        expectation_json: JsonValue | None,
    ) -> tuple[EvaluationTarget, object, Evaluator, object]:
        """Validate generated-case material without creating a fake Case DTO."""

        target = self._targets.get((target_kind, target_key, input_version))
        if target is None:
            raise TargetNotRegisteredError(f"Unknown target {target_kind.value}:{target_key}:v{input_version}.")
        evaluator = self._evaluators.get((evaluator_key, evaluator_version))
        if evaluator is None:
            raise EvaluatorNotRegisteredError(f"Unknown evaluator {evaluator_key}:v{evaluator_version}.")
        return (
            target,
            target.validate_input(input_json),
            evaluator,
            evaluator.validate_expectation(expectation_json),
        )

    async def execute_validated_target(
        self,
        *,
        target: EvaluationTarget,
        input_value: object,
        context: EvaluationContext,
        resources: ResourcesT,
    ) -> TargetExecution:
        """Execute generated-case material after explicit contract validation."""

        return await target.execute(
            input_value,
            context=context,
            service_identity=self.service_identity,
            resources=resources,
        )


def _target_registry(
    targets: tuple[EvaluationTarget, ...],
) -> dict[tuple[TargetKind, str, int], EvaluationTarget]:
    registry: dict[tuple[TargetKind, str, int], EvaluationTarget] = {}
    for target in targets:
        if not isinstance(target, EvaluationTarget):
            raise HarnessConfigurationError("targets must contain SDK EvaluationTarget declarations.")
        identity = (target.kind, target.key, target.input_version)
        if identity in registry:
            raise HarnessConfigurationError(
                f"Duplicate target {target.kind.value}:{target.key}:v{target.input_version}."
            )
        registry[identity] = target
    return registry


def _evaluator_registry(
    evaluators: tuple[Evaluator, ...],
) -> dict[tuple[str, int], Evaluator]:
    registry: dict[tuple[str, int], Evaluator] = {}
    for evaluator in evaluators:
        if not isinstance(evaluator, Evaluator):
            raise HarnessConfigurationError("evaluators must contain SDK Evaluator declarations.")
        identity = (evaluator.key, evaluator.version)
        if identity in registry:
            raise HarnessConfigurationError(f"Duplicate evaluator {evaluator.key}:v{evaluator.version}.")
        registry[identity] = evaluator
    return registry
