"""Adversarial producer tests for portable, outcome-safe diagnostics."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel, ConfigDict

from junjo import (
    Agent,
    AgentLimits,
    BaseState,
    BaseStore,
    Graph,
    Hooks,
    ModelDriverBinding,
    ModelDriverDescriptor,
    Node,
    RunConcurrent,
    Workflow,
)
from junjo.agent import AgentModelError, FinalOutputResponse
from junjo.agent.testing import ScriptedError, ScriptedModelDriver


class DiagnosticState(BaseState):
    pass


class DiagnosticStore(BaseStore[DiagnosticState]):
    pass


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class ThrowingTextError(RuntimeError):
    def __str__(self) -> str:
        raise AssertionError("exception text must not be evaluated unsafely")


class ThrowingTextValue:
    def __str__(self) -> str:
        raise AssertionError("diagnostic text must not replace cancellation")


class RaisingNode(Node[DiagnosticStore]):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def service(self, store: DiagnosticStore) -> None:
        raise self.error


class BlockingNode(Node[DiagnosticStore]):
    def __init__(self, entered: asyncio.Event) -> None:
        super().__init__()
        self.entered = entered

    async def service(self, store: DiagnosticStore) -> None:
        self.entered.set()
        await asyncio.Event().wait()


class HostileHook:
    """Callable whose display metadata and raised error are both untrusted."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def __getattribute__(self, name: str) -> object:
        if name in {"__class__", "__module__", "__name__", "__qualname__"}:
            raise AssertionError("callback metadata must be best effort")
        return object.__getattribute__(self, name)

    def __call__(self, event: object) -> None:
        raise object.__getattribute__(self, "_error")


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)
    return exporter


def _descriptor() -> ModelDriverDescriptor:
    return ModelDriverDescriptor(
        driver_key="diagnostic-test",
        provider="junjo",
        model="scripted-v1",
    )


def _agent(
    driver: object,
    *,
    hooks: Hooks | None = None,
) -> Agent[AgentInput, AgentOutput, None]:
    return Agent(
        key="diagnostic_agent",
        name="Diagnostic Agent",
        instructions="Return deterministic test output.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=_descriptor(),
            driver=driver,  # type: ignore[arg-type]
        ),
        tools=[],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=1, tool_calls=1),
        hooks=hooks,
    )


def _workflow_with_concurrent_node(
    node_factory,
    *,
    hooks: Hooks | None = None,
) -> Workflow[DiagnosticState, DiagnosticStore]:
    def graph_factory() -> Graph:
        concurrent = RunConcurrent("Diagnostic Concurrent", [node_factory()])
        return Graph(source=concurrent, sinks=[concurrent], edges=[])

    return Workflow(
        name="Diagnostic Workflow",
        graph_factory=graph_factory,
        store_factory=lambda: DiagnosticStore(initial_state=DiagnosticState()),
        hooks=hooks,
    )


def _assert_portable_spans(spans: Iterable[ReadableSpan]) -> None:
    for span in spans:
        span.name.encode("utf-8", errors="strict")
        if span.status.description is not None:
            span.status.description.encode("utf-8", errors="strict")
        _assert_portable_attributes(span.attributes or {})
        for event in span.events:
            event.name.encode("utf-8", errors="strict")
            _assert_portable_attributes(event.attributes or {})


def _assert_portable_attributes(attributes: Any) -> None:
    for key, value in attributes.items():
        key.encode("utf-8", errors="strict")
        _assert_portable_attribute_value(value)


def _assert_portable_attribute_value(value: object) -> None:
    if isinstance(value, str):
        value.encode("utf-8", errors="strict")
    elif isinstance(value, tuple | list):
        for item in value:
            _assert_portable_attribute_value(item)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (RuntimeError("broken\ud800message"), "broken\N{REPLACEMENT CHARACTER}message"),
        (ThrowingTextError(), "<exception message unavailable>"),
    ],
)
async def test_workflow_node_and_run_concurrent_failure_diagnostics_are_portable(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
    error: Exception,
    expected_message: str,
) -> None:
    monkeypatch.setattr("junjo.workflow.logger.exception", lambda *args, **kwargs: None)
    workflow = _workflow_with_concurrent_node(lambda: RaisingNode(error))

    try:
        await workflow.execute()
    except Exception as caught:
        assert caught is error
    else:
        pytest.fail("the original Node failure was not propagated")

    spans = span_exporter.get_finished_spans()
    failed = [
        span for span in spans if span.attributes.get("junjo.span_type") in {"workflow", "run_concurrent", "node"}
    ]
    assert len(failed) == 3
    for span in failed:
        assert span.status.description == expected_message
        exception_event = next(event for event in span.events if event.name == "exception")
        assert exception_event.attributes["exception.message"] == expected_message
    _assert_portable_spans(spans)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "expected_reason"),
    [
        ("caller\ud800cancelled", "caller\N{REPLACEMENT CHARACTER}cancelled"),
        (ThrowingTextValue(), "cancelled"),
    ],
)
async def test_workflow_and_run_concurrent_cancellation_diagnostics_are_portable(
    span_exporter: InMemorySpanExporter,
    reason: object,
    expected_reason: str,
) -> None:
    entered = asyncio.Event()
    cancelled_hook_reasons: list[str] = []
    hooks = Hooks()
    hooks.on_workflow_cancelled(lambda event: cancelled_hook_reasons.append(event.reason))
    workflow = _workflow_with_concurrent_node(
        lambda: BlockingNode(entered),
        hooks=hooks,
    )
    task = asyncio.create_task(workflow.execute())
    await entered.wait()
    task.cancel(reason)

    try:
        await task
    except asyncio.CancelledError as caught:
        assert caught.args and caught.args[0] is reason
    else:
        pytest.fail("the caller cancellation was not propagated")

    spans = span_exporter.get_finished_spans()
    workflow_span = next(span for span in spans if span.name == "Diagnostic Workflow")
    concurrent_span = next(span for span in spans if span.name == "Diagnostic Concurrent")
    child_span = next(span for span in spans if span.name == "BlockingNode")
    assert workflow_span.attributes["junjo.cancelled_reason"] == expected_reason
    assert concurrent_span.attributes["junjo.cancelled_reason"] == expected_reason
    assert child_span.attributes["junjo.cancelled_reason"] == "cancelled"
    assert cancelled_hook_reasons == [expected_reason]
    _assert_portable_spans(spans)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hook_error", "expected_message"),
    [
        (RuntimeError("hook\ud800failure"), "hook\N{REPLACEMENT CHARACTER}failure"),
        (ThrowingTextError(), "<exception message unavailable>"),
    ],
)
async def test_hook_failure_diagnostics_are_portable_and_observer_isolated(
    span_exporter: InMemorySpanExporter,
    hook_error: Exception,
    expected_message: str,
) -> None:
    hooks = Hooks()
    observed: list[str] = []
    hooks.on_workflow_started(HostileHook(hook_error))
    hooks.on_workflow_started(lambda event: observed.append(event.hook_name))
    workflow = _workflow_with_concurrent_node(_NoopNode, hooks=hooks)

    result = await workflow.execute()

    assert result.state == DiagnosticState()
    assert observed == ["workflow_started"]
    spans = span_exporter.get_finished_spans()
    workflow_span = next(span for span in spans if span.name == "Diagnostic Workflow")
    hook_event = next(event for event in workflow_span.events if event.name == "junjo.hook_error")
    assert hook_event.attributes["junjo.hook.error.message"] == expected_message
    assert hook_event.attributes["exception.message"] == expected_message
    _assert_portable_spans(spans)


class _NoopNode(Node[DiagnosticStore]):
    async def service(self, store: DiagnosticStore) -> None:
        return None


@pytest.mark.asyncio
async def test_agent_selected_error_survives_throwing_error_string(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
) -> None:
    def throwing_error_string(self: AgentModelError) -> str:
        raise AssertionError("typed Agent error text must not select a new outcome")

    monkeypatch.setattr(AgentModelError, "__str__", throwing_error_string)
    failed_hooks: list[AgentModelError] = []
    hooks = Hooks()
    hooks.on_agent_failed(lambda event: failed_hooks.append(event.error))
    agent = _agent(
        ScriptedModelDriver([ScriptedError(RuntimeError("provider failed"))]),
        hooks=hooks,
    )

    try:
        await agent.execute(AgentInput(value="question"), dependencies=None)
    except AgentModelError as caught:
        assert caught.termination_reason == "model_error"
        assert isinstance(caught.__cause__, RuntimeError)
    else:
        pytest.fail("the selected AgentModelError was not propagated")

    assert len(failed_hooks) == 1
    spans = span_exporter.get_finished_spans()
    failed = [span for span in spans if span.status.status_code.name == "ERROR"]
    assert len(failed) == 2
    for span in failed:
        assert span.status.description == "<exception message unavailable>"
        exception_event = next(event for event in span.events if event.name == "exception")
        assert exception_event.attributes["exception.message"] == "<exception message unavailable>"
    _assert_portable_spans(spans)


@pytest.mark.asyncio
async def test_agent_cancellation_reason_projection_preserves_original_cancellation(
    span_exporter: InMemorySpanExporter,
) -> None:
    entered = asyncio.Event()

    class BlockingDriver:
        async def request(self, request: object) -> object:
            entered.set()
            await asyncio.Event().wait()

    cancelled_hook_reasons: list[str] = []
    hooks = Hooks()
    hooks.on_agent_cancelled(lambda event: cancelled_hook_reasons.append(event.reason))
    agent = _agent(BlockingDriver(), hooks=hooks)
    reason = ThrowingTextValue()
    task = asyncio.create_task(agent.execute(AgentInput(value="question"), dependencies=None))
    await entered.wait()
    task.cancel(reason)

    try:
        await task
    except asyncio.CancelledError as caught:
        assert caught.args and caught.args[0] is reason
    else:
        pytest.fail("the original Agent cancellation was not propagated")

    assert cancelled_hook_reasons == ["cancelled"]
    spans = span_exporter.get_finished_spans()
    cancelled = [span for span in spans if span.attributes.get("junjo.cancelled") is True]
    assert len(cancelled) == 2
    assert all(span.attributes["junjo.cancelled_reason"] == "cancelled" for span in cancelled)
    _assert_portable_spans(spans)


@pytest.mark.asyncio
async def test_agent_hook_failure_with_throwing_text_cannot_replace_success(
    span_exporter: InMemorySpanExporter,
) -> None:
    hooks = Hooks()
    observed: list[str] = []
    hooks.on_agent_started(HostileHook(ThrowingTextError()))
    hooks.on_agent_started(lambda event: observed.append(event.hook_name))
    agent = _agent(
        ScriptedModelDriver([FinalOutputResponse(output={"value": "done"})]),
        hooks=hooks,
    )

    result = await agent.execute(AgentInput(value="question"), dependencies=None)

    assert result.output == AgentOutput(value="done")
    assert observed == ["agent_started"]
    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    hook_event = next(event for event in owner.events if event.name == "junjo.hook_error")
    assert hook_event.attributes["junjo.hook.error.message"] == "<exception message unavailable>"
    _assert_portable_spans(spans)
