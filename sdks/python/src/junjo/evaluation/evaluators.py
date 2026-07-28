"""SDK-owned evaluator contracts and small deterministic built-ins."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError
from typing_extensions import TypeForm

from .context import EvaluationContext, EvaluationRole

ExpectationT = TypeVar("ExpectationT")
CallbackResultT = TypeVar("CallbackResultT")
ResourcesT = TypeVar("ResourcesT")


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Validated terminal judgment returned by every evaluator."""

    passed: bool
    score: float
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.passed, bool):
            raise TypeError("EvaluationResult passed must be a bool.")
        if (
            not isinstance(self.score, (int, float))
            or isinstance(self.score, bool)
            or not 0.0 <= float(self.score) <= 1.0
        ):
            raise ValueError("EvaluationResult score must be between 0.0 and 1.0.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("EvaluationResult reason must be non-empty.")
        if len(self.reason) > 4_096:
            raise ValueError("EvaluationResult reason must be at most 4096 characters.")


class EvaluatorContractError(ValueError):
    """An evaluator declaration or expectation is invalid."""


class EvaluatorExecutionError(RuntimeError):
    """An evaluator callback failed or returned an invalid result."""


class Evaluator:
    """Runtime interface shared by SDK-owned and application callback evaluators."""

    key: str
    version: int
    role: EvaluationRole
    timeout_seconds: float

    def validate_expectation(self, expectation_json: JsonValue | None) -> object:
        raise NotImplementedError

    async def evaluate(
        self,
        *,
        subject: object,
        expectation: object,
        context: EvaluationContext,
        resources: object,
    ) -> EvaluationResult:
        raise NotImplementedError


class _ExactExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected: JsonValue


class ExactMatchEvaluator(Evaluator):
    """Compare a projected subject with one explicit JSON expected value."""

    def __init__(
        self,
        *,
        key: str = "junjo.exact",
        version: int = 1,
        timeout_seconds: float = 30.0,
    ) -> None:
        _validate_evaluator_registration(
            key=key,
            version=version,
            timeout_seconds=timeout_seconds,
        )
        self.key = key
        self.version = version
        self.role = EvaluationRole.VERIFIER
        self.timeout_seconds = timeout_seconds

    def validate_expectation(
        self,
        expectation_json: JsonValue | None,
    ) -> _ExactExpectation:
        try:
            return _ExactExpectation.model_validate(expectation_json)
        except ValidationError as error:
            raise EvaluatorContractError("Exact-match expectation must contain exactly one expected value.") from error

    async def evaluate(
        self,
        *,
        subject: object,
        expectation: object,
        context: EvaluationContext,
        resources: object,
    ) -> EvaluationResult:
        del context, resources
        expected = cast(_ExactExpectation, expectation).expected
        passed = subject == expected
        return EvaluationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason="Subject exactly matched the expected value."
            if passed
            else "Subject did not exactly match the expected value.",
        )


class _StructuredFieldsExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fields: dict[str, JsonValue] = Field(min_length=1, max_length=128)


class StructuredFieldEvaluator(Evaluator):
    """Verify explicit top-level fields on a mapping or Pydantic model."""

    def __init__(
        self,
        *,
        key: str = "junjo.structured_fields",
        version: int = 1,
        timeout_seconds: float = 30.0,
    ) -> None:
        _validate_evaluator_registration(
            key=key,
            version=version,
            timeout_seconds=timeout_seconds,
        )
        self.key = key
        self.version = version
        self.role = EvaluationRole.VERIFIER
        self.timeout_seconds = timeout_seconds

    def validate_expectation(
        self,
        expectation_json: JsonValue | None,
    ) -> _StructuredFieldsExpectation:
        try:
            return _StructuredFieldsExpectation.model_validate(expectation_json)
        except ValidationError as error:
            raise EvaluatorContractError(
                "Structured-field expectation requires one or more explicit fields."
            ) from error

    async def evaluate(
        self,
        *,
        subject: object,
        expectation: object,
        context: EvaluationContext,
        resources: object,
    ) -> EvaluationResult:
        del context, resources
        if isinstance(subject, BaseModel):
            values: Mapping[str, object] = subject.model_dump(mode="python")
        elif isinstance(subject, Mapping):
            values = cast(Mapping[str, object], subject)
        else:
            raise EvaluatorExecutionError("Structured-field evaluator requires a mapping or Pydantic model subject.")
        expected_fields = cast(_StructuredFieldsExpectation, expectation).fields
        mismatches = [
            name for name, expected in expected_fields.items() if name not in values or values[name] != expected
        ]
        passed = not mismatches
        return EvaluationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=(
                "All expected structured fields matched."
                if passed
                else f"Structured fields did not match: {', '.join(sorted(mismatches))}."
            ),
        )


class CallbackEvaluator(Evaluator, Generic[ExpectationT, ResourcesT]):
    """Run an application callback that returns the SDK ``EvaluationResult``."""

    def __init__(
        self,
        *,
        key: str,
        version: int,
        expectation_type: TypeForm[ExpectationT],  # ty: ignore[invalid-type-form]
        callback: Callable[
            [object, ExpectationT, EvaluationContext, ResourcesT],
            EvaluationResult | Awaitable[EvaluationResult],
        ],
        role: EvaluationRole = EvaluationRole.JUDGE,
        timeout_seconds: float = 60.0,
    ) -> None:
        _validate_evaluator_registration(
            key=key,
            version=version,
            timeout_seconds=timeout_seconds,
        )
        if role not in {EvaluationRole.JUDGE, EvaluationRole.VERIFIER}:
            raise EvaluatorContractError("Evaluator callbacks must use the judge or verifier role.")
        self.key = key
        self.version = version
        self.role = role
        self.timeout_seconds = timeout_seconds
        self._callback = callback
        try:
            self._expectation_adapter = TypeAdapter(expectation_type)
        except Exception as error:
            raise EvaluatorContractError(
                f"Unable to construct expectation contract for evaluator {key}:v{version}."
            ) from error

    def validate_expectation(self, expectation_json: JsonValue | None) -> ExpectationT:
        try:
            return self._expectation_adapter.validate_python(expectation_json)
        except ValidationError as error:
            raise EvaluatorContractError(f"Expectation does not match evaluator {self.key}:v{self.version}.") from error

    async def evaluate(
        self,
        *,
        subject: object,
        expectation: object,
        context: EvaluationContext,
        resources: object,
    ) -> EvaluationResult:
        result = await _resolve(
            self._callback(
                subject,
                cast(ExpectationT, expectation),
                context,
                cast(ResourcesT, resources),
            )
        )
        if not isinstance(result, EvaluationResult):
            raise EvaluatorExecutionError(f"Evaluator {self.key}:v{self.version} must return EvaluationResult.")
        return result


class BooleanPredicateEvaluator(CallbackEvaluator[ExpectationT, ResourcesT]):
    """Adapt a domain predicate into a deterministic evaluation result."""

    def __init__(
        self,
        *,
        key: str,
        version: int,
        expectation_type: TypeForm[ExpectationT],  # ty: ignore[invalid-type-form]
        predicate: Callable[
            [object, ExpectationT, EvaluationContext, ResourcesT],
            bool | Awaitable[bool],
        ],
        passed_reason: str = "Boolean predicate passed.",
        failed_reason: str = "Boolean predicate failed.",
        timeout_seconds: float = 30.0,
    ) -> None:
        _validate_reason(passed_reason)
        _validate_reason(failed_reason)

        async def callback(
            subject: object,
            expectation: ExpectationT,
            context: EvaluationContext,
            resources: ResourcesT,
        ) -> EvaluationResult:
            passed = await _resolve(predicate(subject, expectation, context, resources))
            if not isinstance(passed, bool):
                raise EvaluatorExecutionError(f"Boolean evaluator {key}:v{version} predicate must return bool.")
            return EvaluationResult(
                passed=passed,
                score=1.0 if passed else 0.0,
                reason=passed_reason if passed else failed_reason,
            )

        super().__init__(
            key=key,
            version=version,
            expectation_type=expectation_type,
            callback=callback,
            role=EvaluationRole.VERIFIER,
            timeout_seconds=timeout_seconds,
        )


async def _resolve(
    value: CallbackResultT | Awaitable[CallbackResultT],
) -> CallbackResultT:
    if inspect.isawaitable(value):
        return await cast(Awaitable[CallbackResultT], value)
    return cast(CallbackResultT, value)


def _validate_evaluator_registration(
    *,
    key: str,
    version: int,
    timeout_seconds: float,
) -> None:
    if not isinstance(key, str) or not key.strip() or len(key) > 128:
        raise EvaluatorContractError("Evaluator key must be a non-empty string of at most 128 characters.")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise EvaluatorContractError("Evaluator version must be a positive integer.")
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or not 0 < float(timeout_seconds) <= 3_600
    ):
        raise EvaluatorContractError("Evaluator timeout_seconds must be greater than 0 and at most 3600.")


def _validate_reason(reason: str) -> None:
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 4_096:
        raise EvaluatorContractError("Boolean evaluator reasons must be non-empty and at most 4096 characters.")
