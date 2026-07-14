from __future__ import annotations

import json

import jsonpatch
import pytest
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from pydantic import BaseModel

from junjo import (
    Agent,
    AgentLimits,
    ExecutionCorrelation,
    ModelDriverBinding,
    ModelDriverDescriptor,
    Tool,
)
from junjo.agent import (
    AgentInputValidationError,
    AgentModelResponseError,
    AgentToolOutputValidationError,
    FinalOutputResponse,
    ModelUsage,
    ToolCall,
    ToolCallsResponse,
)
from junjo.agent.testing import ScriptedModelDriver


class Input(BaseModel):
    value: str


class Output(BaseModel):
    value: str


class PortableInput(BaseModel):
    value: int | str


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


def agent_for(script, *, tools=()) -> Agent:
    return Agent(
        key="telemetry_agent",
        name="Telemetry Agent",
        instructions="Emit complete evidence.",
        input_type=Input,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=ScriptedModelDriver(script),
        ),
        tools=tools,
        output_type=Output,
        limits=AgentLimits(model_requests=4, tool_calls=4),
    )


@pytest.mark.asyncio
async def test_agent_owner_and_operations_emit_complete_v2_reconstructable_evidence(
    span_exporter: InMemorySpanExporter,
) -> None:
    agent = agent_for(
        [
            FinalOutputResponse(
                output={"value": "done"},
                usage=ModelUsage(input_tokens=0, output_tokens=2, total_tokens=2),
            )
        ]
    )

    result = await agent.execute(Input(value="question"), dependencies=None)
    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    model = next(
        span for span in spans if span.attributes.get("junjo.agent.operation_type") == "model_request"
    )

    assert owner.attributes["junjo.telemetry.contract_version"] == 2
    assert owner.attributes["junjo.executable_definition_id"] == agent.definition_id
    assert owner.attributes["junjo.executable_runtime_id"] == result.run_id
    assert owner.attributes["junjo.agent.runtime_id"] == result.run_id
    assert owner.attributes["junjo.executable_structural_id"] == agent.structural_id
    assert owner.attributes["junjo.agent.state.available"] is True
    assert owner.attributes["junjo.agent.operation.count"] == 1
    assert owner.attributes["junjo.agent.model_request.count"] == 1
    assert owner.attributes["junjo.store.revision.start"] == 0
    assert owner.attributes["junjo.store.revision.end"] == 3
    assert owner.attributes["junjo.store.transition.count"] == 3
    assert owner.attributes["junjo.store.reconstructable"] is True
    assert owner.attributes["junjo.agent.outcome"] == "completed"
    assert owner.attributes["junjo.agent.termination_reason"] == "final_output"
    assert json.loads(owner.attributes["junjo.agent.usage"])["fields"]["inputTokens"] == {
        "sum": 0,
        "observations": 1,
    }
    for root in (
        "junjo.agent.definition_snapshot",
        "junjo.agent.input",
        "junjo.agent.state.start",
        "junjo.agent.state.end",
        "junjo.agent.output",
    ):
        assert owner.attributes[f"{root}.mode"] == "full"
        assert owner.attributes[f"{root}.policy"] == "junjo.full.v1"

    assert "junjo.span_type" not in model.attributes
    assert model.attributes["junjo.agent.operation.sequence"] == 1
    assert model.attributes["junjo.agent.model_request.ordinal"] == 1
    assert model.attributes["junjo.agent.model_request.state_revision"] == 1
    assert model.attributes["junjo.agent.model.response_candidate.available"] is True
    assert model.attributes["junjo.agent.model.response_type"] == "final_output"
    assert json.loads(model.attributes["junjo.agent.model.request"])["runId"] == result.run_id

    start = json.loads(owner.attributes["junjo.agent.state.start"])
    expected_end = json.loads(owner.attributes["junjo.agent.state.end"])
    transitions = sorted(
        (
            event
            for span in spans
            for event in span.events
            if event.name == "set_state"
        ),
        key=lambda event: event.attributes["junjo.store.transition.sequence"],
    )
    projection = start
    for sequence, event in enumerate(transitions, start=1):
        assert event.attributes["junjo.store.transition.sequence"] == sequence
        assert event.attributes["junjo.state_json_patch.mode"] == "full"
        assert event.attributes["junjo.state_json_patch.policy"] == "junjo.full.v1"
        patch = json.loads(event.attributes["junjo.state_json_patch"])
        assert isinstance(patch, list)
        projection = jsonpatch.JsonPatch(patch).apply(projection, in_place=False)
    assert projection == expected_end
    assert [event.attributes["junjo.store.action"] for event in transitions] == [
        "record_model_start",
        "record_model_response",
        "commit_success",
    ]


@pytest.mark.asyncio
async def test_standalone_agent_under_non_junjo_span_keeps_only_physical_parentage(
    span_exporter: InMemorySpanExporter,
) -> None:
    agent = agent_for([FinalOutputResponse(output={"value": "done"})])
    tracer = trace.get_tracer("external-http-server")

    with tracer.start_as_current_span("POST /chat", kind=SpanKind.SERVER) as http_span:
        http_span_id = http_span.get_span_context().span_id
        result = await agent.execute(Input(value="question"), dependencies=None)

    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    model = next(
        span
        for span in spans
        if span.attributes.get("junjo.agent.operation_type") == "model_request"
    )

    assert result.output.value == "done"
    assert owner.parent is not None
    assert owner.parent.span_id == http_span_id
    assert model.parent is not None
    assert model.parent.span_id == owner.context.span_id
    assert not any(key.startswith("junjo.parent_executable_") for key in owner.attributes)


@pytest.mark.asyncio
async def test_standalone_agent_correlation_is_owner_only(
    span_exporter: InMemorySpanExporter,
) -> None:
    agent = agent_for([FinalOutputResponse(output={"value": "done"})])

    await agent.execute(
        Input(value="question"),
        dependencies=None,
        correlation=ExecutionCorrelation(type="test.turn", id="turn-1"),
    )

    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    model = next(
        span
        for span in spans
        if span.attributes.get("junjo.agent.operation_type") == "model_request"
    )
    assert owner.attributes["junjo.correlation.type"] == "test.turn"
    assert owner.attributes["junjo.correlation.id"] == "turn-1"
    assert "junjo.correlation.type" not in model.attributes
    assert "junjo.correlation.id" not in model.attributes


@pytest.mark.parametrize(
    ("correlation_type", "correlation_id"),
    [
        ("", "turn-1"),
        ("test.turn", ""),
        ("test.\ud800", "turn-1"),
        ("test.turn", "turn-\ud800"),
    ],
)
def test_execution_correlation_rejects_nonportable_identity(
    correlation_type: str,
    correlation_id: str,
) -> None:
    with pytest.raises(ValueError):
        ExecutionCorrelation(type=correlation_type, id=correlation_id)


@pytest.mark.asyncio
async def test_agent_ijson_rejection_never_leaks_unencodable_otlp_evidence(
    span_exporter: InMemorySpanExporter,
) -> None:
    rejected_driver = ScriptedModelDriver([FinalOutputResponse(output={"value": "unused"})])
    rejected = Agent(
        key="portable_agent",
        name="Portable Agent",
        instructions="Keep every boundary portable.",
        input_type=PortableInput,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=rejected_driver,
        ),
        tools=[],
        output_type=Output,
    )

    with pytest.raises(AgentInputValidationError):
        await rejected.execute(
            PortableInput(value=9_007_199_254_740_992),
            dependencies=None,
        )

    assert rejected_driver.requests == ()
    rejected_owner = next(
        span
        for span in span_exporter.get_finished_spans()
        if span.attributes.get("junjo.agent.key") == "portable_agent"
    )
    assert rejected_owner.attributes["junjo.agent.state.available"] is False
    assert rejected_owner.attributes["junjo.agent.input_candidate.available"] is False
    assert "junjo.agent.input" not in rejected_owner.attributes

    accepted_driver = ScriptedModelDriver([FinalOutputResponse(output={"value": "done"})])
    accepted = Agent(
        key="portable_max_agent",
        name="Portable Max Agent",
        instructions="Accept the inclusive I-JSON integer limit.",
        input_type=PortableInput,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=accepted_driver,
        ),
        tools=[],
        output_type=Output,
    )
    result = await accepted.execute(
        PortableInput(value=9_007_199_254_740_991),
        dependencies=None,
    )

    assert result.output.value == "done"
    assert accepted_driver.requests[0].to_json()["messages"] == [
        {"type": "agent_input", "input": {"value": 9_007_199_254_740_991}}
    ]
    encoded = encode_spans(span_exporter.get_finished_spans())
    assert encoded.SerializeToString()


@pytest.mark.asyncio
async def test_tool_operation_sequence_counts_and_state_revisions_are_owner_scoped(
    span_exporter: InMemorySpanExporter,
) -> None:
    async def service(input: Args, context) -> ToolOutput:
        return ToolOutput(value=input.value.upper())

    tool = Tool(
        name="upper",
        description="Uppercase a value.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=service,
    )
    agent = agent_for(
        [
            ToolCallsResponse(
                tool_calls=[ToolCall(id="upper-1", name="upper", arguments={"value": "x"})]
            ),
            FinalOutputResponse(output={"value": "X"}),
        ],
        tools=[tool],
    )

    result = await agent.execute(Input(value="x"), dependencies=None)

    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    operations = sorted(
        (span for span in spans if "junjo.agent.operation_type" in span.attributes),
        key=lambda span: span.attributes["junjo.agent.operation.sequence"],
    )
    assert [span.attributes["junjo.agent.operation.sequence"] for span in operations] == [1, 2, 3]
    assert [span.attributes["junjo.agent.operation_type"] for span in operations] == [
        "model_request",
        "tool",
        "model_request",
    ]
    assert all(span.attributes["junjo.agent.runtime_id"] == result.run_id for span in operations)
    tool_span = operations[1]
    assert tool_span.attributes["junjo.agent.tool_call.ordinal"] == 1
    assert tool_span.attributes["junjo.agent.tool.state_revision.before"] == 3
    assert tool_span.attributes["junjo.agent.tool.state_revision.after"] == 5
    assert owner.attributes["junjo.agent.operation.count"] == 3
    assert owner.attributes["junjo.agent.tool_call.requested_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.admitted_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.started_count"] == 1
    assert owner.attributes["junjo.agent.tool_call.completed_count"] == 1


@pytest.mark.asyncio
async def test_nonserializable_model_and_tool_candidates_are_explicitly_unavailable(
    span_exporter: InMemorySpanExporter,
) -> None:
    class NonJson:
        pass

    model_agent = agent_for([NonJson()])
    with pytest.raises(AgentModelResponseError):
        await model_agent.execute(Input(value="x"), dependencies=None)
    model_span = next(
        span
        for span in span_exporter.get_finished_spans()
        if span.attributes.get("junjo.agent.operation_type") == "model_request"
    )
    assert model_span.attributes["junjo.agent.model.response_candidate.available"] is False
    assert (
        model_span.attributes["junjo.agent.model.response_candidate.unavailable_reason"]
        == "not_json_serializable"
    )

    async def bad_result(input: Args, context):
        return NonJson()

    tool = Tool(
        name="bad",
        description="Return a non-JSON value.",
        input_type=Args,
        output_type=ToolOutput,
        shared_service=bad_result,
    )
    tool_agent = agent_for(
        [
            ToolCallsResponse(
                tool_calls=[ToolCall(id="bad", name="bad", arguments={"value": "x"})]
            )
        ],
        tools=[tool],
    )
    with pytest.raises(AgentToolOutputValidationError):
        await tool_agent.execute(Input(value="x"), dependencies=None)
    tool_span = next(
        span
        for span in span_exporter.get_finished_spans()
        if span.attributes.get("junjo.agent.operation_type") == "tool"
    )
    assert tool_span.attributes["junjo.agent.tool.result_candidate.available"] is False
    assert (
        tool_span.attributes["junjo.agent.tool.result_candidate.unavailable_reason"]
        == "not_json_serializable"
    )


@pytest.mark.asyncio
async def test_explicit_null_usage_remains_failed_candidate_evidence(
    span_exporter: InMemorySpanExporter,
) -> None:
    agent = agent_for(
        [
            {
                "v": 1,
                "type": "final_output",
                "output": {"value": "must not validate"},
                "usage": None,
            }
        ]
    )

    with pytest.raises(AgentModelResponseError):
        await agent.execute(Input(value="x"), dependencies=None)

    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "agent")
    model = next(
        span
        for span in spans
        if span.attributes.get("junjo.agent.operation_type") == "model_request"
    )
    assert owner.attributes["junjo.agent.outcome"] == "failed"
    assert owner.attributes["junjo.agent.termination_reason"] == "model_response_error"
    assert model.attributes["junjo.agent.model.response_candidate.available"] is True
    assert json.loads(model.attributes["junjo.agent.model.response_candidate"])["usage"] is None
    assert "junjo.agent.model.response_type" not in model.attributes
    assert "junjo.agent.model.response" not in model.attributes
    assert "junjo.agent.model.usage" not in model.attributes


@pytest.mark.asyncio
async def test_python_store_patch_generation_is_repeatable_for_identical_runs(
    span_exporter: InMemorySpanExporter,
) -> None:
    async def execute_once() -> list[tuple[str, str]]:
        span_exporter.clear()
        agent = agent_for([FinalOutputResponse(output={"value": "done"})])
        await agent.execute(Input(value="same"), dependencies=None)
        events = sorted(
            (
                event
                for span in span_exporter.get_finished_spans()
                for event in span.events
                if event.name == "set_state"
            ),
            key=lambda event: event.attributes["junjo.store.transition.sequence"],
        )
        return [
            (
                event.attributes["junjo.store.action"],
                event.attributes["junjo.state_json_patch"],
            )
            for event in events
        ]

    assert await execute_once() == await execute_once()
