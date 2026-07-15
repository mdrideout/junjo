from __future__ import annotations

import asyncio
import json

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from junjo import Agent, AgentLimits, Hooks, ModelDriverBinding, ModelDriverDescriptor, Tool
from junjo.agent import (
    AgentAdmissionError,
    AgentInternalError,
    AgentLimitExceededError,
    AgentModelError,
    AgentModelResponseError,
    AgentOutputValidationError,
    AgentToolError,
    AgentToolOutputValidationError,
    FinalOutputResponse,
    ToolCall,
    ToolCallsResponse,
)
from junjo.agent import _runtime as agent_runtime
from junjo.agent._state import AgentStore
from junjo.agent.testing import ScriptedError, ScriptedModelDriver


class Input(BaseModel):
    value: str


class Output(BaseModel):
    value: str


class Args(BaseModel):
    value: str


class ToolOutput(BaseModel):
    value: str


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)
    return exporter


def agent_for_driver(
    driver,
    *,
    tools=(),
    limits: AgentLimits | None = None,
    hooks: Hooks | None = None,
) -> Agent:
    return Agent(
        key="failure_agent",
        name="Failure Agent",
        instructions="Be deterministic.",
        input_type=Input,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="test",
                provider="test",
                model="test-model",
            ),
            driver=driver,
        ),
        tools=tools,
        output_type=Output,
        limits=limits or AgentLimits(model_requests=3, tool_calls=3),
        hooks=hooks,
    )


@pytest.mark.asyncio
async def test_model_and_response_failures_are_distinct_and_preserve_causes() -> None:
    cause = RuntimeError("provider down")
    model_failure = agent_for_driver(ScriptedModelDriver([ScriptedError(cause)]))
    with pytest.raises(AgentModelError) as raised:
        await model_failure.execute(Input(value="x"), dependencies=None)
    assert raised.value.__cause__ is cause
    assert raised.value.state.model_request_count == 1
    assert raised.value.state.terminal_reason == "model_error"

    malformed = agent_for_driver(
        ScriptedModelDriver([{"v": 1, "type": "final_output", "output": {"value": "x"}, "extra": 1}])
    )
    with pytest.raises(AgentModelResponseError) as malformed_raised:
        await malformed.execute(Input(value="x"), dependencies=None)
    assert malformed_raised.value.state.terminal_reason == "model_response_error"


@pytest.mark.asyncio
async def test_crafted_malformed_typed_response_is_contained_as_model_response_error(
    span_exporter: InMemorySpanExporter,
) -> None:
    malformed = object.__new__(ToolCallsResponse)
    object.__setattr__(malformed, "tool_calls", ("not-a-tool-call",))
    object.__setattr__(malformed, "assistant_text", None)
    object.__setattr__(malformed, "usage", None)
    agent = agent_for_driver(ScriptedModelDriver([malformed]))

    with pytest.raises(AgentModelResponseError) as raised:
        await agent.execute(Input(value="x"), dependencies=None)

    assert raised.value.state.terminal_reason == "model_response_error"
    model = next(
        span
        for span in span_exporter.get_finished_spans()
        if span.attributes.get("junjo.agent.operation_type") == "model_request"
    )
    assert model.attributes["junjo.agent.model.response_candidate.available"] is False
    assert model.attributes["junjo.agent.model.response_candidate.unavailable_reason"] == "not_json_serializable"


@pytest.mark.asyncio
async def test_model_limit_is_checked_before_an_unstarted_request() -> None:
    async def service(input: Args, context) -> ToolOutput:
        return ToolOutput(value=input.value)

    tool = Tool(
        name="echo",
        description="Echo one value.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=service,
    )
    driver = ScriptedModelDriver(
        [
            ToolCallsResponse(tool_calls=[ToolCall(id="one", name="echo", arguments={"value": "x"})]),
            FinalOutputResponse(output={"value": "must not run"}),
        ]
    )
    agent = agent_for_driver(
        driver,
        tools=[tool],
        limits=AgentLimits(model_requests=1, tool_calls=1),
    )

    with pytest.raises(AgentLimitExceededError) as raised:
        await agent.execute(Input(value="x"), dependencies=None)

    assert raised.value.limit_kind == "model_requests"
    assert raised.value.attempted_count == 2
    assert len(driver.requests) == 1
    assert raised.value.state.model_request_count == 1


@pytest.mark.asyncio
async def test_tool_factory_service_output_and_agent_output_failures_are_typed() -> None:
    factory_cause = RuntimeError("factory failed")

    def bad_factory():
        raise factory_cause

    factory_tool = Tool(
        name="factory",
        description="Fail in construction.",
        input_type=Args,
        output_type=ToolOutput,
        factory=bad_factory,
    )
    factory_agent = agent_for_driver(
        ScriptedModelDriver(
            [ToolCallsResponse(tool_calls=[ToolCall(id="factory-call", name="factory", arguments={"value": "x"})])]
        ),
        tools=[factory_tool],
    )
    with pytest.raises(AgentToolError) as factory_error:
        await factory_agent.execute(Input(value="x"), dependencies=None)
    assert factory_error.value.__cause__ is factory_cause
    assert factory_error.value.state.tool_call_admitted_count == 1
    assert factory_error.value.state.tool_call_started_count == 0

    async def bad_output(input: Args, context):
        return {"wrong": input.value}

    output_tool = Tool(
        name="bad_output",
        description="Return malformed output.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=bad_output,
    )
    tool_output_agent = agent_for_driver(
        ScriptedModelDriver(
            [ToolCallsResponse(tool_calls=[ToolCall(id="bad-output", name="bad_output", arguments={"value": "x"})])]
        ),
        tools=[output_tool],
    )
    with pytest.raises(AgentToolOutputValidationError) as output_error:
        await tool_output_agent.execute(Input(value="x"), dependencies=None)
    assert output_error.value.state.tool_call_started_count == 1
    assert output_error.value.state.tool_call_completed_count == 0

    final_output_agent = agent_for_driver(ScriptedModelDriver([FinalOutputResponse(output={"wrong": "x"})]))
    with pytest.raises(AgentOutputValidationError) as final_error:
        await final_output_agent.execute(Input(value="x"), dependencies=None)
    assert final_error.value.state.terminal_reason == "output_validation_error"
    assert final_error.value.state.final_output_available is False


@pytest.mark.asyncio
async def test_direct_tool_service_failure_is_typed_and_preserves_cause() -> None:
    cause = RuntimeError("service failed")

    async def failing_service(input: Args, context) -> ToolOutput:
        raise cause

    tool = Tool(
        name="service_failure",
        description="Fail during service invocation.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=failing_service,
    )
    agent = agent_for_driver(
        ScriptedModelDriver(
            [
                ToolCallsResponse(
                    tool_calls=[
                        ToolCall(
                            id="service-failure",
                            name="service_failure",
                            arguments={"value": "x"},
                        )
                    ]
                )
            ]
        ),
        tools=[tool],
    )

    with pytest.raises(AgentToolError) as raised:
        await agent.execute(Input(value="x"), dependencies=None)

    assert raised.value.__cause__ is cause
    assert raised.value.state.tool_call_started_count == 1
    assert raised.value.state.tool_call_completed_count == 0


@pytest.mark.asyncio
async def test_nonterminal_hook_failure_is_isolated_before_success() -> None:
    hooks = Hooks()
    calls: list[str] = []

    def fail_started(event) -> None:
        calls.append("failed observer")
        raise RuntimeError("observer failed")

    hooks.on_agent_started(fail_started)
    hooks.on_agent_started(lambda event: calls.append("later observer"))
    agent = agent_for_driver(
        ScriptedModelDriver([FinalOutputResponse(output={"value": "done"})]),
        hooks=hooks,
    )

    result = await agent.execute(Input(value="x"), dependencies=None)

    assert result.output.value == "done"
    assert calls == ["failed observer", "later observer"]


@pytest.mark.asyncio
async def test_cancel_during_model_marks_operation_and_owner_without_failure(
    span_exporter: InMemorySpanExporter,
) -> None:
    entered = asyncio.Event()

    class BlockingDriver:
        async def request(self, request):
            entered.set()
            await asyncio.Event().wait()

    lifecycle: list[str] = []
    hooks = Hooks()
    hooks.on_agent_started(lambda event: lifecycle.append("started"))
    hooks.on_agent_cancelled(lambda event: lifecycle.append("cancelled"))
    hooks.on_agent_failed(lambda event: lifecycle.append("failed"))
    agent = agent_for_driver(BlockingDriver(), hooks=hooks)
    task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
    await entered.wait()
    task.cancel("stop model")

    with pytest.raises(asyncio.CancelledError):
        await task

    assert lifecycle == ["started", "cancelled"]
    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    model = next(span for span in spans if span.attributes.get("junjo.agent.operation_type") == "model_request")
    assert owner.attributes["junjo.agent.outcome"] == "cancelled"
    assert owner.attributes["junjo.agent.termination_reason"] == "cancelled"
    assert owner.attributes["junjo.cancelled"] is True
    assert model.attributes["junjo.cancelled"] is True
    assert owner.status.status_code.name == "UNSET"


@pytest.mark.asyncio
async def test_cancel_during_tool_propagates_and_no_new_operation_starts(
    span_exporter: InMemorySpanExporter,
) -> None:
    entered = asyncio.Event()

    async def blocking_tool(input: Args, context) -> ToolOutput:
        entered.set()
        await asyncio.Event().wait()
        return ToolOutput(value=input.value)

    tool = Tool(
        name="block",
        description="Block until cancelled.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=blocking_tool,
    )
    driver = ScriptedModelDriver(
        [
            ToolCallsResponse(tool_calls=[ToolCall(id="block", name="block", arguments={"value": "x"})]),
            FinalOutputResponse(output={"value": "must not run"}),
        ]
    )
    agent = agent_for_driver(driver, tools=[tool])
    task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
    await entered.wait()
    task.cancel("stop tool")
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(driver.requests) == 1
    tool_span = next(
        span
        for span in span_exporter.get_finished_spans()
        if span.attributes.get("junjo.agent.operation_type") == "tool"
    )
    assert tool_span.attributes["junjo.cancelled"] is True


@pytest.mark.asyncio
async def test_cancel_during_model_start_does_not_publish_a_semantic_operation(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
) -> None:
    entered = asyncio.Event()
    driver = ScriptedModelDriver([FinalOutputResponse(output={"value": "unused"})])

    async def block_model_start(self, ordinal: int) -> int:
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(AgentStore, "record_model_start", block_model_start)
    agent = agent_for_driver(driver)
    task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
    await entered.wait()
    task.cancel("cancel model start")

    with pytest.raises(asyncio.CancelledError):
        await task

    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    assert owner.attributes["junjo.agent.operation.count"] == 0
    assert owner.attributes["junjo.agent.model_request.count"] == 0
    assert not any("junjo.agent.operation_type" in span.attributes for span in spans)
    assert driver.requests == ()


@pytest.mark.asyncio
async def test_internal_failure_during_model_start_does_not_publish_a_semantic_operation(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
) -> None:
    cause = RuntimeError("model start bookkeeping failed")
    driver = ScriptedModelDriver([FinalOutputResponse(output={"value": "unused"})])

    async def fail_model_start(self, ordinal: int) -> int:
        raise cause

    monkeypatch.setattr(AgentStore, "record_model_start", fail_model_start)
    agent = agent_for_driver(driver)

    with pytest.raises(AgentInternalError) as raised:
        await agent.execute(Input(value="x"), dependencies=None)

    assert raised.value.__cause__ is cause
    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    assert owner.attributes["junjo.agent.operation.count"] == 0
    assert owner.attributes["junjo.agent.model_request.count"] == 0
    assert not any("junjo.agent.operation_type" in span.attributes for span in spans)
    assert driver.requests == ()


@pytest.mark.parametrize("boundary", ["revision", "started"])
@pytest.mark.asyncio
async def test_cancel_during_tool_start_does_not_publish_a_semantic_tool_operation(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
    boundary: str,
) -> None:
    entered = asyncio.Event()
    service_calls = 0

    async def service(input: Args, context) -> ToolOutput:
        nonlocal service_calls
        service_calls += 1
        return ToolOutput(value=input.value)

    async def block_revision(self) -> int:
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def block_started(self) -> int:
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    if boundary == "revision":
        monkeypatch.setattr(AgentStore, "_get_store_revision", block_revision)
    else:
        monkeypatch.setattr(AgentStore, "record_tool_started", block_started)
    tool = Tool(
        name="start_boundary",
        description="Exercise Tool start bookkeeping.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=service,
    )
    agent = agent_for_driver(
        ScriptedModelDriver(
            [
                ToolCallsResponse(
                    tool_calls=[
                        ToolCall(
                            id="start-boundary",
                            name="start_boundary",
                            arguments={"value": "x"},
                        )
                    ]
                )
            ]
        ),
        tools=[tool],
    )
    task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
    await entered.wait()
    task.cancel(f"cancel Tool {boundary}")

    with pytest.raises(asyncio.CancelledError):
        await task

    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    operations = [span for span in spans if "junjo.agent.operation_type" in span.attributes]
    assert [span.attributes["junjo.agent.operation_type"] for span in operations] == ["model_request"]
    assert owner.attributes["junjo.agent.operation.count"] == 1
    assert owner.attributes["junjo.agent.tool_call.requested_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.admitted_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.started_count"] == 0
    assert service_calls == 0


@pytest.mark.parametrize("boundary", ["revision", "started"])
@pytest.mark.asyncio
async def test_internal_failure_during_tool_start_does_not_publish_a_semantic_tool_operation(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
    boundary: str,
) -> None:
    cause = RuntimeError(f"Tool {boundary} bookkeeping failed")
    service_calls = 0

    async def service(input: Args, context) -> ToolOutput:
        nonlocal service_calls
        service_calls += 1
        return ToolOutput(value=input.value)

    async def fail_revision(self) -> int:
        raise cause

    async def fail_started(self) -> int:
        raise cause

    if boundary == "revision":
        monkeypatch.setattr(AgentStore, "_get_store_revision", fail_revision)
    else:
        monkeypatch.setattr(AgentStore, "record_tool_started", fail_started)
    tool = Tool(
        name="start_failure",
        description="Exercise Tool start bookkeeping failure.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=service,
    )
    agent = agent_for_driver(
        ScriptedModelDriver(
            [
                ToolCallsResponse(
                    tool_calls=[
                        ToolCall(
                            id="start-failure",
                            name="start_failure",
                            arguments={"value": "x"},
                        )
                    ]
                )
            ]
        ),
        tools=[tool],
    )

    with pytest.raises(AgentInternalError) as raised:
        await agent.execute(Input(value="x"), dependencies=None)

    assert raised.value.__cause__ is cause
    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    operations = [span for span in spans if "junjo.agent.operation_type" in span.attributes]
    assert [span.attributes["junjo.agent.operation_type"] for span in operations] == ["model_request"]
    assert owner.attributes["junjo.agent.operation.count"] == 1
    assert owner.attributes["junjo.agent.tool_call.requested_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.admitted_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.started_count"] == 0
    assert service_calls == 0


@pytest.mark.parametrize("failure_kind", ["cancelled", "internal"])
@pytest.mark.asyncio
async def test_malformed_tool_preflight_revision_failure_does_not_publish_tool_operation(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
    failure_kind: str,
) -> None:
    entered = asyncio.Event()
    cause = RuntimeError("malformed Tool revision failed")

    async def fail_revision(self) -> int:
        if failure_kind == "cancelled":
            entered.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")
        raise cause

    monkeypatch.setattr(AgentStore, "_get_store_revision", fail_revision)
    tool = Tool(
        name="typed",
        description="Require typed arguments.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=lambda input, context: ToolOutput(value=input.value),
    )
    agent = agent_for_driver(
        ScriptedModelDriver(
            [ToolCallsResponse(tool_calls=[ToolCall(id="malformed", name="typed", arguments={"wrong": "x"})])]
        ),
        tools=[tool],
    )

    if failure_kind == "cancelled":
        task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
        await entered.wait()
        task.cancel("cancel malformed Tool preflight")
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(AgentInternalError) as raised:
            await agent.execute(Input(value="x"), dependencies=None)
        assert raised.value.__cause__ is cause

    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    operations = [span for span in spans if "junjo.agent.operation_type" in span.attributes]
    assert [span.attributes["junjo.agent.operation_type"] for span in operations] == ["model_request"]
    assert owner.attributes["junjo.agent.operation.count"] == 1
    assert owner.attributes["junjo.agent.tool_call.requested_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.admitted_count"] == 0
    assert owner.attributes["junjo.agent.tool_call.started_count"] == 0


@pytest.mark.parametrize("post_commit_failure", ["cancelled", "internal"])
@pytest.mark.asyncio
async def test_tool_result_revision_is_returned_by_commit_without_a_second_await(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
    post_commit_failure: str,
) -> None:
    original_revision = AgentStore._get_store_revision
    revision_reads = 0

    async def fail_second_revision_read(self) -> int:
        nonlocal revision_reads
        revision_reads += 1
        if revision_reads > 1:
            if post_commit_failure == "cancelled":
                raise asyncio.CancelledError("post-result revision cancelled")
            raise RuntimeError("post-result revision failed")
        return await original_revision(self)

    monkeypatch.setattr(AgentStore, "_get_store_revision", fail_second_revision_read)

    async def service(input: Args, context) -> ToolOutput:
        return ToolOutput(value=input.value)

    tool = Tool(
        name="result_receipt",
        description="Return a committed result revision.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=service,
    )
    agent = agent_for_driver(
        ScriptedModelDriver(
            [
                ToolCallsResponse(
                    tool_calls=[
                        ToolCall(
                            id="result-receipt",
                            name="result_receipt",
                            arguments={"value": "x"},
                        )
                    ]
                ),
                FinalOutputResponse(output={"value": "done"}),
            ]
        ),
        tools=[tool],
    )

    result = await agent.execute(Input(value="x"), dependencies=None)

    assert result.output.value == "done"
    assert revision_reads == 1
    tool_span = next(
        span
        for span in span_exporter.get_finished_spans()
        if span.attributes.get("junjo.agent.operation_type") == "tool"
    )
    assert "junjo.agent.tool.result" in tool_span.attributes
    assert tool_span.attributes["junjo.agent.tool.state_revision.after"] == 5


@pytest.mark.asyncio
async def test_cancellation_during_model_response_commit_keeps_state_and_usage_coherent(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
) -> None:
    entered = asyncio.Event()

    async def block_response_commit(self, response, usage) -> None:
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(AgentStore, "record_model_response", block_response_commit)
    agent = agent_for_driver(ScriptedModelDriver([FinalOutputResponse(output={"value": "unused"})]))
    task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
    await entered.wait()
    task.cancel("cancel response commit")

    with pytest.raises(asyncio.CancelledError):
        await task

    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    model = next(span for span in spans if span.attributes.get("junjo.agent.operation_type") == "model_request")
    state_end = json.loads(owner.attributes["junjo.agent.state.end"])
    usage = json.loads(owner.attributes["junjo.agent.usage"])
    assert model.attributes["junjo.agent.model.response_candidate.available"] is True
    assert "junjo.agent.model.response" not in model.attributes
    assert model.attributes["junjo.cancelled"] is True
    assert usage == {"v": 1, "modelResponses": 0, "fields": {}}
    assert state_end["usage"] == usage
    assert state_end["final_output_available"] is False
    assert owner.attributes["junjo.store.reconstructable"] is True


@pytest.mark.asyncio
async def test_cancellation_during_tool_result_commit_keeps_pending_call_truthful(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
) -> None:
    entered = asyncio.Event()

    async def service(input: Args, context) -> ToolOutput:
        return ToolOutput(value=input.value)

    async def block_result_commit(self, *, call_id, tool_name, result) -> None:
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(AgentStore, "record_tool_result", block_result_commit)
    tool = Tool(
        name="commit_block",
        description="Return one validated value.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=service,
    )
    agent = agent_for_driver(
        ScriptedModelDriver(
            [
                ToolCallsResponse(
                    tool_calls=[
                        ToolCall(
                            id="commit-block",
                            name="commit_block",
                            arguments={"value": "x"},
                        )
                    ]
                ),
                FinalOutputResponse(output={"value": "unused"}),
            ]
        ),
        tools=[tool],
    )
    task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
    await entered.wait()
    task.cancel("cancel result commit")

    with pytest.raises(asyncio.CancelledError):
        await task

    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    tool_span = next(span for span in spans if span.attributes.get("junjo.agent.operation_type") == "tool")
    state_end = json.loads(owner.attributes["junjo.agent.state.end"])
    assert tool_span.attributes["junjo.agent.tool.result_candidate.available"] is True
    assert "junjo.agent.tool.result" not in tool_span.attributes
    assert tool_span.attributes["junjo.cancelled"] is True
    assert owner.attributes["junjo.agent.tool_call.requested_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.admitted_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.started_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.completed_count"] == 0
    assert state_end["pending_tool_call_ids"] == ["commit-block"]
    assert state_end["completed_tool_call_ids"] == []
    assert owner.attributes["junjo.store.reconstructable"] is True


@pytest.mark.parametrize("first_outcome", ["failed", "cancelled"])
@pytest.mark.asyncio
async def test_admitted_multi_tool_batch_stops_after_first_failed_or_cancelled_call(
    span_exporter: InMemorySpanExporter,
    first_outcome: str,
) -> None:
    entered = asyncio.Event()
    first_calls = 0
    later_factory_calls = 0

    async def first_service(input: Args, context) -> ToolOutput:
        nonlocal first_calls
        first_calls += 1
        if first_outcome == "cancelled":
            entered.set()
            await asyncio.Event().wait()
        raise RuntimeError("first service failed")

    async def later_service(input: Args, context) -> ToolOutput:
        return ToolOutput(value=input.value)

    def later_factory():
        nonlocal later_factory_calls
        later_factory_calls += 1
        return later_service

    first_tool = Tool(
        name="first",
        description="Fail or block first.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=first_service,
    )
    later_tool = Tool(
        name="later",
        description="Must never start.",
        input_type=Args,
        output_type=ToolOutput,
        factory=later_factory,
    )
    agent = agent_for_driver(
        ScriptedModelDriver(
            [
                ToolCallsResponse(
                    tool_calls=[
                        ToolCall(id="first", name="first", arguments={"value": "one"}),
                        ToolCall(id="later", name="later", arguments={"value": "two"}),
                    ]
                )
            ]
        ),
        tools=[first_tool, later_tool],
    )

    if first_outcome == "cancelled":
        task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
        await entered.wait()
        task.cancel("cancel first call")
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(AgentToolError):
            await agent.execute(Input(value="x"), dependencies=None)

    assert first_calls == 1
    assert later_factory_calls == 0
    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    tool_spans = [span for span in spans if span.attributes.get("junjo.agent.operation_type") == "tool"]
    assert len(tool_spans) == 1
    assert tool_spans[0].attributes["junjo.agent.tool_call.id"] == "first"
    assert owner.attributes["junjo.agent.tool_call.requested_count"] == 2
    assert owner.attributes["junjo.agent.tool_call.admitted_count"] == 2
    assert owner.attributes["junjo.agent.tool_call.started_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.completed_count"] == 0


@pytest.mark.asyncio
async def test_terminal_observer_cancellation_does_not_rewrite_completed_outcome(
    span_exporter: InMemorySpanExporter,
) -> None:
    observer_entered = asyncio.Event()
    hooks = Hooks()

    async def block_completed(event) -> None:
        observer_entered.set()
        await asyncio.Event().wait()

    hooks.on_agent_completed(block_completed)
    agent = agent_for_driver(
        ScriptedModelDriver([FinalOutputResponse(output={"value": "done"})]),
        hooks=hooks,
    )
    task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
    await observer_entered.wait()
    task.cancel("stop observer delivery")
    with pytest.raises(asyncio.CancelledError):
        await task

    owner = next(
        span for span in span_exporter.get_finished_spans() if span.attributes.get("junjo.span_type") == "agent"
    )
    assert owner.attributes["junjo.agent.outcome"] == "completed"
    assert owner.attributes["junjo.agent.termination_reason"] == "final_output"
    assert "junjo.cancelled" not in owner.attributes
    assert [event.name for event in owner.events].count("junjo.hook_delivery_cancelled") == 1


@pytest.mark.asyncio
async def test_failure_observer_mutation_cannot_corrupt_raised_error_evidence() -> None:
    hooks = Hooks()

    def corrupt(event) -> None:
        event.error.state.terminal_reason = "observer-corruption"
        event.state.terminal_reason = "observer-state-corruption"

    hooks.on_agent_failed(corrupt)
    cause = RuntimeError("provider down")
    agent = agent_for_driver(
        ScriptedModelDriver([ScriptedError(cause)]),
        hooks=hooks,
    )

    with pytest.raises(AgentModelError) as raised:
        await agent.execute(Input(value="x"), dependencies=None)

    assert raised.value.state.terminal_reason == "model_error"
    assert raised.value.evidence.terminal_reason == "model_error"


@pytest.mark.asyncio
async def test_unexpected_admitted_runtime_failure_is_explicit_internal_error(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
) -> None:
    cause = RuntimeError("Junjo completion preparation failed")

    async def fail_completion(self, response) -> None:
        raise cause

    monkeypatch.setattr(agent_runtime._AgentRun, "_complete", fail_completion)
    agent = agent_for_driver(ScriptedModelDriver([FinalOutputResponse(output={"value": "unused"})]))

    with pytest.raises(AgentInternalError) as raised:
        await agent.execute(Input(value="x"), dependencies=None)

    assert raised.value.termination_reason == "internal_error"
    assert raised.value.__cause__ is cause
    assert raised.value.state.terminal_reason == "internal_error"
    owner = next(
        span for span in span_exporter.get_finished_spans() if span.attributes.get("junjo.span_type") == "agent"
    )
    model = next(
        span
        for span in span_exporter.get_finished_spans()
        if span.attributes.get("junjo.agent.operation_type") == "model_request"
    )
    assert owner.attributes["junjo.store.reconstructable"] is True
    assert owner.attributes["junjo.agent.operation.count"] == 1
    assert model.attributes["junjo.agent.model.response_type"] == "final_output"
    assert "junjo.agent.model.response" in model.attributes


@pytest.mark.asyncio
async def test_admission_preparation_failure_is_typed_before_state_publication(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
) -> None:
    cause = RuntimeError("initial evidence failed")

    def fail_initial_evidence(self):
        raise cause

    monkeypatch.setattr(
        AgentStore,
        "_get_initial_store_owner_evidence",
        fail_initial_evidence,
    )
    hooks = Hooks()
    lifecycle: list[str] = []
    hooks.on_agent_started(lambda event: lifecycle.append("started"))
    driver = ScriptedModelDriver([FinalOutputResponse(output={"value": "unused"})])
    agent = agent_for_driver(driver, hooks=hooks)

    with pytest.raises(AgentAdmissionError) as raised:
        await agent.execute(Input(value="x"), dependencies=None)

    assert raised.value.__cause__ is cause
    assert raised.value.termination_reason == "internal_error"
    assert lifecycle == []
    assert driver.requests == ()
    owner = next(
        span for span in span_exporter.get_finished_spans() if span.attributes.get("junjo.span_type") == "agent"
    )
    assert owner.attributes["junjo.agent.state.available"] is False
    assert owner.attributes["junjo.agent.outcome"] == "failed"
    assert owner.attributes["junjo.agent.termination_reason"] == "internal_error"
    assert owner.attributes["error.type"] == "AgentAdmissionError"
    assert "junjo.agent.store.id" not in owner.attributes
    assert "junjo.agent.input" not in owner.attributes
    assert "junjo.agent.state.start" not in owner.attributes


@pytest.mark.parametrize("selected_outcome", ["completed", "failed", "cancelled"])
@pytest.mark.asyncio
async def test_terminal_commit_failure_supersedes_selected_outcome_once(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
    selected_outcome: str,
) -> None:
    cause = RuntimeError(f"{selected_outcome} terminal commit failed")
    original_set_terminal = AgentStore.set_terminal_reason

    async def fail_success(self, output) -> None:
        raise cause

    async def fail_selected_reason(self, reason: str) -> None:
        if reason == ("model_error" if selected_outcome == "failed" else "cancelled"):
            raise cause
        await original_set_terminal(self, reason)

    if selected_outcome == "completed":
        monkeypatch.setattr(AgentStore, "commit_success", fail_success)
    else:
        monkeypatch.setattr(AgentStore, "set_terminal_reason", fail_selected_reason)

    hooks = Hooks()
    lifecycle: list[str] = []
    hooks.on_agent_started(lambda event: lifecycle.append("started"))
    hooks.on_agent_completed(lambda event: lifecycle.append("completed"))
    hooks.on_agent_failed(lambda event: lifecycle.append("failed"))
    hooks.on_agent_cancelled(lambda event: lifecycle.append("cancelled"))

    if selected_outcome == "failed":
        driver = ScriptedModelDriver([ScriptedError(RuntimeError("provider failed"))])
    elif selected_outcome == "cancelled":
        entered = asyncio.Event()

        class BlockingDriver:
            async def request(self, request):
                entered.set()
                await asyncio.Event().wait()

        driver = BlockingDriver()
    else:
        driver = ScriptedModelDriver([FinalOutputResponse(output={"value": "done"})])
    agent = agent_for_driver(driver, hooks=hooks)

    if selected_outcome == "cancelled":
        task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
        await entered.wait()
        task.cancel("caller cancelled")
        with pytest.raises(AgentInternalError) as raised:
            await task
    else:
        with pytest.raises(AgentInternalError) as raised:
            await agent.execute(Input(value="x"), dependencies=None)

    assert raised.value.__cause__ is cause
    assert raised.value.superseded_outcome == selected_outcome
    assert raised.value.state.terminal_reason == "internal_error"
    assert lifecycle == ["started", "failed"]
    owner = next(
        span for span in span_exporter.get_finished_spans() if span.attributes.get("junjo.span_type") == "agent"
    )
    assert owner.attributes["junjo.agent.outcome"] == "failed"
    assert owner.attributes["junjo.agent.termination_reason"] == "internal_error"
    assert owner.attributes["error.type"] == "AgentInternalError"
    assert owner.attributes["junjo.store.reconstructable"] is False
    assert [event.name for event in owner.events].count("exception") == 1


@pytest.mark.asyncio
async def test_get_state_internal_failure_uses_last_known_snapshot_without_recursion(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
) -> None:
    cause = RuntimeError("Store read failed")

    async def fail_get_state(self):
        raise cause

    monkeypatch.setattr(AgentStore, "get_state", fail_get_state)
    hooks = Hooks()
    lifecycle: list[str] = []
    hooks.on_agent_failed(lambda event: lifecycle.append("failed"))
    agent = agent_for_driver(
        ScriptedModelDriver([FinalOutputResponse(output={"value": "unused"})]),
        hooks=hooks,
    )

    with pytest.raises(AgentInternalError) as raised:
        await agent.execute(Input(value="x"), dependencies=None)

    assert raised.value.__cause__ is cause
    assert raised.value.state.terminal_reason == "internal_error"
    assert lifecycle == ["failed"]
    owner = next(
        span for span in span_exporter.get_finished_spans() if span.attributes.get("junjo.span_type") == "agent"
    )
    assert owner.attributes["junjo.agent.outcome"] == "failed"
    assert owner.attributes["junjo.agent.termination_reason"] == "internal_error"
    assert owner.attributes["junjo.store.reconstructable"] is False


@pytest.mark.parametrize("terminal_await", ["commit_success", "get_state", "owner_evidence"])
@pytest.mark.asyncio
async def test_cancellation_during_success_terminalization_drains_committed_outcome(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
    terminal_await: str,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    completed_hooks = 0
    original_commit_success = AgentStore.commit_success
    original_get_state = AgentStore.get_state
    original_owner_evidence = AgentStore._get_store_owner_evidence
    owner_evidence_calls = 0

    async def commit_success(self, output) -> None:
        if terminal_await == "commit_success":
            entered.set()
            await release.wait()
        await original_commit_success(self, output)

    async def get_state(self):
        state = await original_get_state(self)
        if terminal_await == "get_state" and state.terminal_reason == "final_output" and not entered.is_set():
            entered.set()
            await release.wait()
        return state

    async def owner_evidence(self):
        nonlocal owner_evidence_calls
        owner_evidence_calls += 1
        if terminal_await == "owner_evidence" and owner_evidence_calls == 1:
            entered.set()
            await release.wait()
        return await original_owner_evidence(self)

    monkeypatch.setattr(AgentStore, "commit_success", commit_success)
    monkeypatch.setattr(AgentStore, "get_state", get_state)
    monkeypatch.setattr(AgentStore, "_get_store_owner_evidence", owner_evidence)
    hooks = Hooks()

    def completed(event) -> None:
        nonlocal completed_hooks
        completed_hooks += 1

    hooks.on_agent_completed(completed)
    agent = agent_for_driver(
        ScriptedModelDriver([FinalOutputResponse(output={"value": "done"})]),
        hooks=hooks,
    )
    task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
    await entered.wait()
    task.cancel(f"cancel during {terminal_await}")
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    owner = next(
        span for span in span_exporter.get_finished_spans() if span.attributes.get("junjo.span_type") == "agent"
    )
    assert owner.attributes["junjo.agent.outcome"] == "completed"
    assert owner.attributes["junjo.agent.termination_reason"] == "final_output"
    assert owner.attributes["junjo.store.reconstructable"] is True
    assert completed_hooks == 1


@pytest.mark.asyncio
async def test_repeated_cancellation_cannot_cancel_terminal_evidence_work(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    original = AgentStore.commit_success

    async def blocked_terminal(self, output) -> None:
        entered.set()
        await release.wait()
        await original(self, output)

    monkeypatch.setattr(AgentStore, "commit_success", blocked_terminal)
    agent = agent_for_driver(ScriptedModelDriver([FinalOutputResponse(output={"value": "done"})]))
    task = asyncio.create_task(agent.execute(Input(value="x"), dependencies=None))
    await entered.wait()
    task.cancel("first cancellation")
    await asyncio.sleep(0)
    task.cancel("second cancellation")
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    owner = next(
        span for span in span_exporter.get_finished_spans() if span.attributes.get("junjo.span_type") == "agent"
    )
    assert owner.attributes["junjo.agent.outcome"] == "completed"
    assert owner.attributes["junjo.store.reconstructable"] is True
