"""Evaluation context, telemetry, registration, and evaluator contracts."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic import BaseModel

from junjo.evaluation import (
    BooleanPredicateEvaluator,
    CallbackEvaluator,
    EvaluationContext,
    EvaluationHarness,
    EvaluationResult,
    EvaluationRole,
    EvaluationRunClass,
    EvaluatorExecutionError,
    ExactMatchEvaluator,
    ExecutionServiceIdentity,
    HarnessConfigurationError,
    StructuredFieldEvaluator,
    evaluation_span,
)

REVISION = "a" * 40


class ExpectedText(BaseModel):
    text: str


def _evaluation_context() -> EvaluationContext:
    return EvaluationContext(
        run_class=EvaluationRunClass.EVALUATION,
        dataset_id="dataset-1",
        run_id="run-1",
        case_id="case-1",
        attempt_id="attempt-1",
        source_revision=REVISION,
    )


def test_evaluation_context_enforces_run_class_identity_shapes() -> None:
    context = _evaluation_context()

    assert context.for_role(EvaluationRole.SUBJECT) == EvaluationContext(
        run_class=EvaluationRunClass.EVALUATION,
        dataset_id="dataset-1",
        run_id="run-1",
        case_id="case-1",
        attempt_id="attempt-1",
        source_revision=REVISION,
        role=EvaluationRole.SUBJECT,
    )
    assert context.role is EvaluationRole.ORCHESTRATOR

    generation = EvaluationContext(
        run_class=EvaluationRunClass.DATASET_GENERATION,
        dataset_id="dataset-1",
        case_key="generated-1",
        source_revision=REVISION,
    )
    assert generation.case_key == "generated-1"
    assert generation.run_id is None

    with pytest.raises(ValueError, match="requires run_id"):
        EvaluationContext(
            run_class=EvaluationRunClass.EVALUATION,
            dataset_id="dataset-1",
            case_id="case-1",
            attempt_id="attempt-1",
            source_revision=REVISION,
        )
    with pytest.raises(ValueError, match="requires case_key"):
        EvaluationContext(
            run_class=EvaluationRunClass.DATASET_GENERATION,
            dataset_id="dataset-1",
            source_revision=REVISION,
        )
    with pytest.raises(TypeError, match="run_class"):
        EvaluationContext(
            run_class="evaluation",  # type: ignore[arg-type]
            dataset_id="dataset-1",
            run_id="run-1",
            case_id="case-1",
            attempt_id="attempt-1",
            source_revision=REVISION,
        )
    with pytest.raises(TypeError, match="role"):
        EvaluationContext(
            run_class=EvaluationRunClass.EVALUATION,
            dataset_id="dataset-1",
            run_id="run-1",
            case_id="case-1",
            attempt_id="attempt-1",
            source_revision=REVISION,
            role="subject",  # type: ignore[arg-type]
        )


def test_evaluation_spans_have_exact_bounded_attributes_and_truthful_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.namespace": "example.apps",
                "service.name": "real-application",
            }
        )
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)

    context = _evaluation_context()
    with evaluation_span(context):
        with evaluation_span(context.for_role(EvaluationRole.SUBJECT)):
            trace.get_tracer("application").start_span("application-child").end()
        with evaluation_span(context.for_role(EvaluationRole.JUDGE)):
            pass
        with evaluation_span(context.for_role(EvaluationRole.VERIFIER)):
            pass

    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert set(spans) == {
        "junjo.evaluation.attempt",
        "junjo.evaluation.subject",
        "junjo.evaluation.judge",
        "junjo.evaluation.verifier",
        "application-child",
    }
    attempt = spans["junjo.evaluation.attempt"]
    assert attempt.attributes == {
        "junjo.evaluation.context.version": 1,
        "junjo.evaluation.run_class": "evaluation",
        "junjo.evaluation.dataset.id": "dataset-1",
        "junjo.evaluation.run.id": "run-1",
        "junjo.evaluation.case.id": "case-1",
        "junjo.evaluation.attempt.id": "attempt-1",
        "junjo.evaluation.source.revision": REVISION,
        "junjo.evaluation.role": "orchestrator",
        "junjo.telemetry.contract_version": 2,
    }
    subject = spans["junjo.evaluation.subject"]
    assert subject.parent is not None
    assert subject.parent.span_id == attempt.context.span_id
    assert subject.attributes is not None
    assert subject.attributes["junjo.evaluation.role"] == "subject"
    child = spans["application-child"]
    assert child.parent is not None
    assert child.parent.span_id == subject.context.span_id
    assert child.attributes is None or not any(key.startswith("junjo.evaluation.") for key in child.attributes)
    for span in spans.values():
        assert span.resource.attributes["service.namespace"] == "example.apps"
        assert span.resource.attributes["service.name"] == "real-application"


def test_dataset_generation_span_omits_nonexistent_control_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)
    context = EvaluationContext(
        run_class=EvaluationRunClass.DATASET_GENERATION,
        dataset_id="dataset-1",
        case_key="generated-1",
        source_revision=REVISION,
    )

    with evaluation_span(context):
        with evaluation_span(context.for_role(EvaluationRole.SUBJECT)):
            pass

    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert set(spans) == {
        "junjo.evaluation.dataset_generation",
        "junjo.evaluation.subject",
    }
    attributes = spans["junjo.evaluation.dataset_generation"].attributes
    assert attributes is not None
    assert attributes["junjo.evaluation.case.key"] == "generated-1"
    assert "junjo.evaluation.case.id" not in attributes
    assert "junjo.evaluation.run.id" not in attributes
    assert "junjo.evaluation.attempt.id" not in attributes


@pytest.mark.asyncio
async def test_deterministic_evaluators_validate_and_score_explicit_contracts() -> None:
    context = _evaluation_context().for_role(EvaluationRole.VERIFIER)
    exact = ExactMatchEvaluator()
    exact_expectation = exact.validate_expectation({"expected": "Brooklyn"})
    assert await exact.evaluate(
        subject="Brooklyn",
        expectation=exact_expectation,
        context=context,
        resources=None,
    ) == EvaluationResult(
        passed=True,
        score=1.0,
        reason="Subject exactly matched the expected value.",
    )

    structured = StructuredFieldEvaluator()
    structured_expectation = structured.validate_expectation(
        {"fields": {"place": "Prospect Park", "borough": "Brooklyn"}}
    )
    mismatch = await structured.evaluate(
        subject={"place": "Prospect Park", "borough": "Queens"},
        expectation=structured_expectation,
        context=context,
        resources=None,
    )
    assert mismatch.passed is False
    assert mismatch.score == 0.0
    assert mismatch.reason == "Structured fields did not match: borough."


@pytest.mark.asyncio
async def test_callback_and_boolean_evaluators_keep_domain_meaning_explicit() -> None:
    received_roles: list[EvaluationRole] = []

    async def judge(
        subject: object,
        expectation: ExpectedText,
        context: EvaluationContext,
        resources: object,
    ) -> EvaluationResult:
        del resources
        received_roles.append(context.role)
        passed = subject == expectation.text
        return EvaluationResult(
            passed=passed,
            score=0.8 if passed else 0.2,
            reason="Domain callback completed.",
        )

    callback = CallbackEvaluator(
        key="app.quality",
        version=1,
        expectation_type=ExpectedText,
        callback=judge,
    )
    expectation = callback.validate_expectation({"text": "match"})
    result = await callback.evaluate(
        subject="match",
        expectation=expectation,
        context=_evaluation_context().for_role(EvaluationRole.JUDGE),
        resources=None,
    )
    assert result.passed is True
    assert received_roles == [EvaluationRole.JUDGE]

    predicate = BooleanPredicateEvaluator(
        key="app.contains",
        version=1,
        expectation_type=ExpectedText,
        predicate=lambda subject, expected, _context, _resources: expected.text in str(subject),
    )
    predicate_expectation = predicate.validate_expectation({"text": "Park"})
    predicate_result = await predicate.evaluate(
        subject="Prospect Park",
        expectation=predicate_expectation,
        context=_evaluation_context().for_role(EvaluationRole.VERIFIER),
        resources=None,
    )
    assert predicate_result == EvaluationResult(
        passed=True,
        score=1.0,
        reason="Boolean predicate passed.",
    )


@pytest.mark.asyncio
async def test_harness_requires_an_explicit_target_registry() -> None:
    async def slow_judge(
        subject: object,
        expectation: ExpectedText,
        context: EvaluationContext,
        resources: object,
    ) -> EvaluationResult:
        del subject, expectation, context, resources
        await asyncio.sleep(0.05)
        return EvaluationResult(passed=True, score=1.0, reason="late")

    evaluator = CallbackEvaluator(
        key="slow",
        version=1,
        expectation_type=ExpectedText,
        callback=slow_judge,
        timeout_seconds=0.001,
    )

    @asynccontextmanager
    async def resources() -> AsyncIterator[None]:
        yield None

    with pytest.raises(HarnessConfigurationError, match="at least one target"):
        EvaluationHarness(
            application_key="app",
            service_identity=ExecutionServiceIdentity(
                service_namespace="example",
                service_name="app",
            ),
            targets=(),
            evaluators=(evaluator,),
            runtime_context=resources,
        )


def test_evaluation_result_and_callback_results_fail_closed() -> None:
    with pytest.raises(ValueError, match="between"):
        EvaluationResult(passed=True, score=1.1, reason="invalid")

    async def invalid_callback(
        subject: object,
        expectation: ExpectedText,
        context: EvaluationContext,
        resources: object,
    ) -> EvaluationResult:
        del subject, expectation, context, resources
        return "not-a-result"  # ty: ignore[invalid-return-type]

    evaluator = CallbackEvaluator(
        key="invalid",
        version=1,
        expectation_type=ExpectedText,
        callback=invalid_callback,
    )

    async def run() -> None:
        with pytest.raises(EvaluatorExecutionError, match="must return"):
            await evaluator.evaluate(
                subject="x",
                expectation=ExpectedText(text="x"),
                context=_evaluation_context().for_role(EvaluationRole.JUDGE),
                resources=None,
            )

    asyncio.run(run())
