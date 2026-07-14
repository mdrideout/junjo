from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_serializer

from junjo import Agent, AgentLimits, Hooks, ModelDriverBinding, ModelDriverDescriptor, Tool
from junjo.agent import (
    AgentHistoryValidationError,
    AgentInputMessage,
    AgentInputValidationError,
    AgentLimitExceededError,
    AgentModelResponseError,
    AgentOutputValidationError,
    AgentToolInputValidationError,
    AgentToolOutputValidationError,
    AgentUnknownToolError,
    AssistantOutputMessage,
    AssistantToolCallsMessage,
    FinalOutputResponse,
    ModelUsage,
    ToolCall,
    ToolCallsResponse,
    ToolResultMessage,
)
from junjo.agent.testing import ScriptedModelDriver


class Question(BaseModel):
    question: str


class Answer(BaseModel):
    answer: str


class LookupInput(BaseModel):
    query: str


class LookupOutput(BaseModel):
    value: str


class IntegerValue(BaseModel):
    value: int


class DefaultedIntegerValue(BaseModel):
    value: int
    label: str = "default"


class AliasedIntegerValue(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    value: int = Field(alias="externalValue")


class SecretValue(BaseModel):
    secret: SecretStr


class OpaqueValue(BaseModel):
    value: object


class LowercasedValue(BaseModel):
    value: str

    @field_serializer("value")
    def serialize_value(self, value: str) -> str:
        return value.lower()


class DatetimeValue(BaseModel):
    value: datetime


def nested_arrays(depth: int) -> object:
    value: object = "leaf"
    for _ in range(depth):
        value = [value]
    return value


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)
    return exporter


def create_agent(
    script: Sequence[object],
    *,
    tools: Sequence[Tool] = (),
    limits: AgentLimits | None = None,
    hooks: Hooks | None = None,
) -> tuple[Agent, ScriptedModelDriver]:
    driver = ScriptedModelDriver(script)
    agent = Agent(
        key="test_agent",
        name="Test Agent",
        instructions="Use only declared evidence.",
        input_type=Question,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=tools,
        output_type=Answer,
        limits=limits or AgentLimits(model_requests=4, tool_calls=4),
        hooks=hooks,
    )
    return agent, driver


def create_integer_agent(
    script: Sequence[object],
    *,
    tools: Sequence[Tool] = (),
    output_type: type[BaseModel] = IntegerValue,
) -> tuple[Agent, ScriptedModelDriver]:
    driver = ScriptedModelDriver(script)
    agent = Agent(
        key="integer_agent",
        name="Integer Agent",
        instructions="Return exact JSON types.",
        input_type=IntegerValue,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=tools,
        output_type=output_type,
        limits=AgentLimits(model_requests=4, tool_calls=4),
    )
    return agent, driver


def create_untyped_agent(
    script: Sequence[object],
    *,
    tools: Sequence[Tool] = (),
) -> tuple[Agent, ScriptedModelDriver]:
    driver = ScriptedModelDriver(script)
    agent = Agent(
        key="depth_agent",
        name="Depth Agent",
        instructions="Preserve bounded JSON exactly.",
        input_type=object,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=tools,
        output_type=object,
    )
    return agent, driver


@pytest.mark.asyncio
async def test_agent_input_and_history_preflight_complete_state_depth() -> None:
    accepted_agent, _driver = create_untyped_agent([{"v": 1, "type": "final_output", "output": "done"}])
    accepted = await accepted_agent.execute(nested_arrays(125), dependencies=None)
    assert accepted.output == "done"

    rejected_agent, rejected_driver = create_untyped_agent([{"v": 1, "type": "final_output", "output": "unused"}])
    with pytest.raises(AgentInputValidationError):
        await rejected_agent.execute(nested_arrays(126), dependencies=None)
    assert rejected_driver.requests == ()

    deep_history = (
        AgentInputMessage(nested_arrays(126)),
        AssistantOutputMessage("complete"),
    )
    history_agent, history_driver = create_untyped_agent([{"v": 1, "type": "final_output", "output": "unused"}])
    with pytest.raises(AgentHistoryValidationError):
        await history_agent.execute("next", dependencies=None, history=deep_history)
    assert history_driver.requests == ()


@pytest.mark.asyncio
async def test_agent_output_and_tool_result_preflight_complete_patch_depth() -> None:
    accepted_output_agent, _driver = create_untyped_agent(
        [{"v": 1, "type": "final_output", "output": nested_arrays(125)}]
    )
    accepted = await accepted_output_agent.execute("go", dependencies=None)
    assert accepted.output == nested_arrays(125)

    rejected_output_agent, _driver = create_untyped_agent(
        [{"v": 1, "type": "final_output", "output": nested_arrays(126)}]
    )
    with pytest.raises(AgentOutputValidationError):
        await rejected_output_agent.execute("go", dependencies=None)

    async def deep_service(input: dict[str, object], context) -> object:
        return nested_arrays(context.dependencies)

    tool = Tool(
        name="deep_result",
        description="Return a configured nested result.",
        input_type=dict[str, object],
        output_type=object,
        shared_service=deep_service,
    )
    script = [
        {
            "v": 1,
            "type": "tool_calls",
            "calls": [{"id": "deep", "name": "deep_result", "arguments": {}}],
        },
        {"v": 1, "type": "final_output", "output": "done"},
    ]
    accepted_tool_agent, _driver = create_untyped_agent(script, tools=[tool])
    assert (await accepted_tool_agent.execute("go", dependencies=125)).output == "done"

    rejected_tool_agent, _driver = create_untyped_agent(script, tools=[tool])
    with pytest.raises(AgentToolOutputValidationError):
        await rejected_tool_agent.execute("go", dependencies=126)


@pytest.mark.asyncio
async def test_tool_call_response_preflights_exact_agent_state_patch_depth() -> None:
    async def service(input: dict[str, object], context) -> str:
        return "ok"

    tool = Tool(
        name="consume",
        description="Consume bounded arguments.",
        input_type=dict[str, object],
        output_type=str,
        shared_service=service,
    )

    def script(depth: int) -> list[object]:
        return [
            {
                "v": 1,
                "type": "tool_calls",
                "calls": [
                    {
                        "id": "consume",
                        "name": "consume",
                        "arguments": {"value": nested_arrays(depth)},
                    }
                ],
            },
            {"v": 1, "type": "final_output", "output": "done"},
        ]

    accepted_agent, _driver = create_untyped_agent(script(122), tools=[tool])
    assert (await accepted_agent.execute("go", dependencies=None)).output == "done"

    rejected_agent, _driver = create_untyped_agent(script(123), tools=[tool])
    with pytest.raises(AgentModelResponseError):
        await rejected_agent.execute("go", dependencies=None)


@pytest.mark.asyncio
async def test_direct_completion_is_typed_detached_and_provider_neutral() -> None:
    hooks = Hooks()

    def mutate_hook_result(event) -> None:
        event.result.output.answer = "mutated by observer"

    hooks.on_agent_completed(mutate_hook_result)
    agent, driver = create_agent(
        [
            FinalOutputResponse(
                output={"answer": "complete"},
                usage=ModelUsage(input_tokens=0, output_tokens=2, total_tokens=2),
            )
        ],
        hooks=hooks,
    )
    caller_input = {"question": "What happened?"}

    result = await agent.execute(caller_input, dependencies={"private": object()})
    caller_input["question"] = "changed later"

    assert isinstance(result.output, Answer)
    assert result.output.answer == "complete"
    assert [message.type for message in result.transcript] == [
        "agent_input",
        "assistant_output",
    ]
    assert result.usage.model_responses == 1
    assert result.usage.fields["inputTokens"].sum == 0
    assert result.model_request_count == 1
    request = driver.requests[0]
    assert request.to_json()["messages"] == [{"type": "agent_input", "input": {"question": "What happened?"}}]
    assert "private" not in request.to_json()


@pytest.mark.asyncio
async def test_ordered_multi_tool_loop_preflights_then_executes_sequentially() -> None:
    calls: list[str] = []
    factory_count = 0

    class LookupService:
        async def __call__(self, input: LookupInput, context) -> LookupOutput:
            calls.append(input.query)
            return LookupOutput(value=input.query.upper())

    def factory() -> LookupService:
        nonlocal factory_count
        factory_count += 1
        return LookupService()

    tool = Tool(
        name="lookup",
        description="Look up one value.",
        input_type=LookupInput,
        output_type=LookupOutput,
        factory=factory,
    )
    agent, driver = create_agent(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(id="call-1", name="lookup", arguments={"query": "one"}),
                    ToolCall(id="call-2", name="lookup", arguments={"query": "two"}),
                ]
            ),
            FinalOutputResponse(output={"answer": "done"}),
        ],
        tools=[tool],
    )

    result = await agent.execute(Question(question="go"), dependencies=None)

    assert calls == ["one", "two"]
    assert factory_count == 1
    assert result.tool_call_requested_count == 2
    assert result.tool_call_admitted_count == 2
    assert result.tool_call_started_count == 2
    assert result.tool_call_completed_count == 2
    assert [message.type for message in result.transcript] == [
        "agent_input",
        "assistant_tool_calls",
        "tool_result",
        "tool_result",
        "assistant_output",
    ]
    second_messages = driver.requests[1].to_json()["messages"]
    assert [message["type"] for message in second_messages] == [
        "agent_input",
        "assistant_tool_calls",
        "tool_result",
        "tool_result",
    ]


@pytest.mark.asyncio
async def test_invalid_second_tool_argument_rejects_entire_batch_before_side_effects(
    span_exporter: InMemorySpanExporter,
) -> None:
    factory_count = 0
    service_calls = 0

    class Service:
        async def __call__(self, input: LookupInput, context) -> LookupOutput:
            nonlocal service_calls
            service_calls += 1
            return LookupOutput(value=input.query)

    def factory() -> Service:
        nonlocal factory_count
        factory_count += 1
        return Service()

    tool = Tool(
        name="lookup",
        description="Look up one value.",
        input_type=LookupInput,
        output_type=LookupOutput,
        factory=factory,
    )
    agent, _driver = create_agent(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(id="valid", name="lookup", arguments={"query": "valid"}),
                    ToolCall(id="invalid", name="lookup", arguments={"wrong": "field"}),
                ]
            )
        ],
        tools=[tool],
    )

    with pytest.raises(AgentToolInputValidationError) as raised:
        await agent.execute(Question(question="go"), dependencies=None)

    assert factory_count == 0
    assert service_calls == 0
    assert raised.value.call_ordinal == 2
    assert raised.value.state.tool_call_requested_count == 2
    assert raised.value.state.tool_call_admitted_count == 0
    tool_spans = [
        span
        for span in span_exporter.get_finished_spans()
        if span.attributes.get("junjo.agent.operation_type") == "tool"
    ]
    assert len(tool_spans) == 1
    assert tool_spans[0].attributes["junjo.agent.tool_call.id"] == "invalid"


@pytest.mark.asyncio
async def test_unknown_and_overbudget_batches_start_no_tool_operation_or_factory(
    span_exporter: InMemorySpanExporter,
) -> None:
    agent, _ = create_agent([ToolCallsResponse(tool_calls=[ToolCall(id="unknown", name="missing", arguments={})])])
    with pytest.raises(AgentUnknownToolError) as unknown:
        await agent.execute(Question(question="go"), dependencies=None)
    assert unknown.value.call_ordinal == 1
    assert all(
        span.attributes.get("junjo.agent.operation_type") != "tool" for span in span_exporter.get_finished_spans()
    )

    factory_calls = 0

    def forbidden_factory():
        nonlocal factory_calls
        factory_calls += 1
        raise AssertionError("factory must not run")

    tool = Tool(
        name="lookup",
        description="Look up.",
        input_type=LookupInput,
        output_type=LookupOutput,
        factory=forbidden_factory,
    )
    overbudget, _ = create_agent(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(id="one", name="lookup", arguments={"query": "one"}),
                    ToolCall(id="two", name="lookup", arguments={"query": "two"}),
                ]
            )
        ],
        tools=[tool],
        limits=AgentLimits(model_requests=2, tool_calls=1),
    )
    with pytest.raises(AgentLimitExceededError) as limited:
        await overbudget.execute(Question(question="go"), dependencies=None)
    assert limited.value.limit_kind == "tool_calls"
    assert limited.value.attempted_count == 2
    assert limited.value.requested_batch_size == 2
    assert limited.value.state.tool_call_admitted_count == 0
    assert factory_calls == 0


@pytest.mark.asyncio
async def test_invocation_rejection_and_history_grammar_start_no_driver_or_hooks(
    span_exporter: InMemorySpanExporter,
) -> None:
    hooks = Hooks()
    lifecycle: list[str] = []
    hooks.on_agent_started(lambda event: lifecycle.append("started"))
    agent, driver = create_agent(
        [FinalOutputResponse(output={"answer": "unused"})],
        hooks=hooks,
    )
    with pytest.raises(AgentInputValidationError):
        await agent.execute({"wrong": "field"}, dependencies=None)
    with pytest.raises(AgentHistoryValidationError):
        await agent.execute(
            Question(question="go"),
            dependencies=None,
            history=[AgentInputMessage({"question": "unresolved"})],
        )

    assert driver.requests == ()
    assert lifecycle == []
    owners = [span for span in span_exporter.get_finished_spans() if span.attributes.get("junjo.span_type") == "agent"]
    assert len(owners) == 2
    assert all(span.attributes["junjo.agent.state.available"] is False for span in owners)
    assert all("junjo.agent.store.id" not in span.attributes for span in owners)


@pytest.mark.asyncio
async def test_history_accepts_only_complete_ordered_exchanges() -> None:
    complete = [
        AgentInputMessage({"question": "old"}),
        AssistantToolCallsMessage(tool_calls=[ToolCall(id="historical", name="lookup", arguments={})]),
        ToolResultMessage(
            tool_call_id="historical",
            tool_name="lookup",
            result={"value": "old"},
        ),
        AssistantOutputMessage({"answer": "old"}),
    ]
    agent, driver = create_agent([FinalOutputResponse(output={"answer": "new"})])

    result = await agent.execute(
        Question(question="new"),
        dependencies=None,
        history=complete,
    )

    assert result.output.answer == "new"
    assert driver.requests[0].to_json()["messages"] == [
        {"type": "agent_input", "input": {"question": "old"}},
        {
            "type": "assistant_tool_calls",
            "calls": [
                {
                    "id": "historical",
                    "name": "lookup",
                    "arguments": {},
                }
            ],
        },
        {
            "type": "tool_result",
            "callId": "historical",
            "toolName": "lookup",
            "result": {"value": "old"},
        },
        {"type": "assistant_output", "output": {"answer": "old"}},
        {"type": "agent_input", "input": {"question": "new"}},
    ]


@pytest.mark.asyncio
async def test_duplicate_tool_call_id_across_responses_is_malformed() -> None:
    async def service(input: LookupInput, context) -> LookupOutput:
        return LookupOutput(value=input.query)

    tool = Tool(
        name="lookup",
        description="Look up.",
        input_type=LookupInput,
        output_type=LookupOutput,
        shared_service=service,
    )
    agent, _ = create_agent(
        [
            ToolCallsResponse(tool_calls=[ToolCall(id="duplicate", name="lookup", arguments={"query": "one"})]),
            ToolCallsResponse(tool_calls=[ToolCall(id="duplicate", name="lookup", arguments={"query": "two"})]),
        ],
        tools=[tool],
    )

    with pytest.raises(AgentModelResponseError):
        await agent.execute(Question(question="go"), dependencies=None)


@pytest.mark.asyncio
async def test_duplicate_ids_within_one_typed_batch_have_zero_admission_or_side_effects() -> None:
    service_calls = 0

    async def service(input: LookupInput, context) -> LookupOutput:
        nonlocal service_calls
        service_calls += 1
        return LookupOutput(value=input.query)

    tool = Tool(
        name="lookup",
        description="Look up.",
        input_type=LookupInput,
        output_type=LookupOutput,
        shared_service=service,
    )
    agent, _ = create_agent(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(id="duplicate", name="lookup", arguments={"query": "one"}),
                    ToolCall(id="duplicate", name="lookup", arguments={"query": "two"}),
                ]
            )
        ],
        tools=[tool],
    )

    with pytest.raises(AgentModelResponseError) as raised:
        await agent.execute(Question(question="go"), dependencies=None)

    assert service_calls == 0
    assert raised.value.state.tool_call_requested_count == 0
    assert raised.value.state.tool_call_admitted_count == 0


@pytest.mark.asyncio
async def test_usage_distinguishes_absent_from_reported_zero_across_responses() -> None:
    async def service(input: LookupInput, context) -> LookupOutput:
        return LookupOutput(value=input.query)

    tool = Tool(
        name="lookup",
        description="Look up.",
        input_type=LookupInput,
        output_type=LookupOutput,
        shared_service=service,
    )
    agent, _ = create_agent(
        [
            ToolCallsResponse(
                tool_calls=[ToolCall(id="usage", name="lookup", arguments={"query": "x"})],
                usage=None,
            ),
            FinalOutputResponse(
                output={"answer": "done"},
                usage=ModelUsage(input_tokens=0),
            ),
        ],
        tools=[tool],
    )

    result = await agent.execute(Question(question="go"), dependencies=None)

    assert result.usage.model_responses == 2
    assert result.usage.fields["inputTokens"].sum == 0
    assert result.usage.fields["inputTokens"].observations == 1
    assert "outputTokens" not in result.usage.fields


@pytest.mark.asyncio
async def test_agent_input_rejects_json_type_coercion_before_driver_invocation() -> None:
    agent, driver = create_integer_agent([FinalOutputResponse(output={"value": 1})])

    with pytest.raises(AgentInputValidationError):
        await agent.execute({"value": "1"}, dependencies=None)

    assert driver.requests == ()


@pytest.mark.asyncio
async def test_tool_arguments_reject_json_type_coercion_before_service_invocation() -> None:
    service_calls = 0

    async def service(input: IntegerValue, context) -> IntegerValue:
        nonlocal service_calls
        service_calls += 1
        return input

    tool = Tool(
        name="integer",
        description="Return one integer.",
        input_type=IntegerValue,
        output_type=IntegerValue,
        shared_service=service,
    )
    agent, _driver = create_integer_agent(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="coerced-argument",
                        name="integer",
                        arguments={"value": "1"},
                    )
                ]
            )
        ],
        tools=[tool],
    )

    with pytest.raises(AgentToolInputValidationError):
        await agent.execute({"value": 1}, dependencies=None)

    assert service_calls == 0


@pytest.mark.asyncio
async def test_tool_result_rejects_json_type_coercion() -> None:
    async def service(input: IntegerValue, context) -> object:
        return {"value": "1"}

    tool = Tool(
        name="integer",
        description="Return one integer.",
        input_type=IntegerValue,
        output_type=IntegerValue,
        shared_service=service,
    )
    agent, _driver = create_integer_agent(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="coerced-result",
                        name="integer",
                        arguments={"value": 1},
                    )
                ]
            )
        ],
        tools=[tool],
    )

    with pytest.raises(AgentToolOutputValidationError):
        await agent.execute({"value": 1}, dependencies=None)


@pytest.mark.asyncio
async def test_final_output_rejects_json_type_coercion() -> None:
    agent, _driver = create_integer_agent([FinalOutputResponse(output={"value": "1"})])

    with pytest.raises(AgentOutputValidationError):
        await agent.execute({"value": 1}, dependencies=None)


@pytest.mark.asyncio
async def test_strict_validation_preserves_declared_defaults() -> None:
    agent, _driver = create_integer_agent(
        [FinalOutputResponse(output={"value": 1})],
        output_type=DefaultedIntegerValue,
    )

    result = await agent.execute({"value": 1}, dependencies=None)

    assert result.output == DefaultedIntegerValue(value=1, label="default")


@pytest.mark.asyncio
async def test_strict_validation_uses_one_symmetric_external_alias() -> None:
    driver = ScriptedModelDriver([FinalOutputResponse(output={"externalValue": 2})])
    agent = Agent(
        key="alias_agent",
        name="Alias Agent",
        instructions="Use the declared external name.",
        input_type=AliasedIntegerValue,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=(),
        output_type=AliasedIntegerValue,
    )

    result = await agent.execute({"externalValue": 1}, dependencies=None)

    assert result.output.value == 2
    assert driver.requests[0].to_json()["messages"] == [{"type": "agent_input", "input": {"externalValue": 1}}]


@pytest.mark.asyncio
async def test_strict_validation_rejects_unadvertised_field_name_even_when_model_allows_it() -> None:
    driver = ScriptedModelDriver([FinalOutputResponse(output={"externalValue": 2})])
    agent = Agent(
        key="alias_agent",
        name="Alias Agent",
        instructions="Use the declared external name.",
        input_type=AliasedIntegerValue,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=(),
        output_type=AliasedIntegerValue,
    )

    with pytest.raises(AgentInputValidationError):
        await agent.execute({"value": 1}, dependencies=None)

    assert driver.requests == ()


@pytest.mark.asyncio
async def test_agent_input_rejects_unknown_members_instead_of_dropping_them() -> None:
    agent, driver = create_integer_agent([FinalOutputResponse(output={"value": 1})])

    with pytest.raises(AgentInputValidationError):
        await agent.execute({"value": 1, "unknown": True}, dependencies=None)

    assert driver.requests == ()


@pytest.mark.asyncio
async def test_tool_arguments_reject_unknown_members_before_service_invocation() -> None:
    service_calls = 0

    async def service(input: IntegerValue, context) -> IntegerValue:
        nonlocal service_calls
        service_calls += 1
        return input

    tool = Tool(
        name="integer",
        description="Return one integer.",
        input_type=IntegerValue,
        output_type=IntegerValue,
        shared_service=service,
    )
    agent, _driver = create_integer_agent(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="unknown-argument",
                        name="integer",
                        arguments={"value": 1, "unknown": True},
                    )
                ]
            )
        ],
        tools=[tool],
    )

    with pytest.raises(AgentToolInputValidationError):
        await agent.execute({"value": 1}, dependencies=None)

    assert service_calls == 0


@pytest.mark.asyncio
async def test_tool_result_rejects_unknown_members_instead_of_dropping_them() -> None:
    async def service(input: IntegerValue, context) -> object:
        return {"value": 1, "unknown": True}

    tool = Tool(
        name="integer",
        description="Return one integer.",
        input_type=IntegerValue,
        output_type=IntegerValue,
        shared_service=service,
    )
    agent, _driver = create_integer_agent(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="unknown-result",
                        name="integer",
                        arguments={"value": 1},
                    )
                ]
            )
        ],
        tools=[tool],
    )

    with pytest.raises(AgentToolOutputValidationError):
        await agent.execute({"value": 1}, dependencies=None)


@pytest.mark.asyncio
async def test_final_output_rejects_unknown_members_instead_of_dropping_them() -> None:
    agent, _driver = create_integer_agent([FinalOutputResponse(output={"value": 1, "unknown": True})])

    with pytest.raises(AgentOutputValidationError):
        await agent.execute({"value": 1}, dependencies=None)


@pytest.mark.asyncio
async def test_final_output_rejects_lossy_declared_serialization() -> None:
    driver = ScriptedModelDriver([FinalOutputResponse(output={"secret": "hunter2"})])
    agent = Agent(
        key="secret_agent",
        name="Secret Agent",
        instructions="Never lose supplied JSON.",
        input_type=IntegerValue,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=(),
        output_type=SecretValue,
    )

    with pytest.raises(AgentOutputValidationError):
        await agent.execute({"value": 1}, dependencies=None)


@pytest.mark.asyncio
async def test_agent_input_rejects_one_shot_iterators_without_consuming_them() -> None:
    yielded = 0

    def values():
        nonlocal yielded
        yielded += 1
        yield 1

    driver = ScriptedModelDriver([FinalOutputResponse(output={"value": 1})])
    agent = Agent(
        key="iterator_agent",
        name="Iterator Agent",
        instructions="Require concrete JSON.",
        input_type=list[int],
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=(),
        output_type=IntegerValue,
    )

    with pytest.raises(AgentInputValidationError):
        await agent.execute(values(), dependencies=None)

    assert yielded == 0
    assert driver.requests == ()


@pytest.mark.asyncio
async def test_tool_result_rejects_one_shot_iterators_without_consuming_them(
    span_exporter: InMemorySpanExporter,
) -> None:
    yielded = 0

    def values():
        nonlocal yielded
        yielded += 1
        yield 1

    async def service(input: IntegerValue, context) -> object:
        return values()

    tool = Tool(
        name="iterator",
        description="Return a concrete array.",
        input_type=IntegerValue,
        output_type=list[int],
        shared_service=service,
    )
    agent, _driver = create_integer_agent(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="iterator-result",
                        name="iterator",
                        arguments={"value": 1},
                    )
                ]
            )
        ],
        tools=[tool],
    )

    with pytest.raises(AgentToolOutputValidationError):
        await agent.execute({"value": 1}, dependencies=None)

    assert yielded == 0
    tool_span = next(
        span
        for span in span_exporter.get_finished_spans()
        if span.attributes.get("junjo.agent.operation_type") == "tool"
    )
    assert tool_span.attributes["junjo.agent.tool.result_candidate.available"] is False
    assert tool_span.attributes["junjo.agent.tool.result_candidate.unavailable_reason"] == "not_json_serializable"


@pytest.mark.asyncio
async def test_agent_input_rejects_non_string_object_keys_before_projection() -> None:
    driver = ScriptedModelDriver([FinalOutputResponse(output={"value": 1})])
    agent = Agent(
        key="mapping_agent",
        name="Mapping Agent",
        instructions="Preserve JSON object names.",
        input_type=dict[str, object],
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=(),
        output_type=IntegerValue,
    )

    with pytest.raises(AgentInputValidationError):
        await agent.execute({"nested": {1: "not portable"}}, dependencies=None)

    assert driver.requests == ()


@pytest.mark.asyncio
async def test_agent_input_rejects_iterator_inside_typed_model_without_consuming_it() -> None:
    yielded = 0

    def values():
        nonlocal yielded
        yielded += 1
        yield 1

    driver = ScriptedModelDriver([FinalOutputResponse(output={"value": 1})])
    agent = Agent(
        key="opaque_agent",
        name="Opaque Agent",
        instructions="Preserve application ownership.",
        input_type=OpaqueValue,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=(),
        output_type=IntegerValue,
    )

    with pytest.raises(AgentInputValidationError):
        await agent.execute(OpaqueValue(value=values()), dependencies=None)

    assert yielded == 0
    assert driver.requests == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("input_type", "input_value"),
    [
        (SecretValue, SecretValue(secret="hunter2")),
        (LowercasedValue, LowercasedValue(value="ABC")),
    ],
)
async def test_agent_input_rejects_lossy_typed_serialization(
    input_type: type[BaseModel],
    input_value: BaseModel,
) -> None:
    driver = ScriptedModelDriver([FinalOutputResponse(output={"value": 1})])
    agent = Agent(
        key="lossless_agent",
        name="Lossless Agent",
        instructions="Preserve typed values.",
        input_type=input_type,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=(),
        output_type=IntegerValue,
    )

    with pytest.raises(AgentInputValidationError):
        await agent.execute(input_value, dependencies=None)

    assert driver.requests == ()


@pytest.mark.asyncio
async def test_tool_result_rejects_lossy_typed_serialization_and_marks_candidate_unavailable(
    span_exporter: InMemorySpanExporter,
) -> None:
    async def service(input: IntegerValue, context) -> SecretValue:
        return SecretValue(secret="hunter2")

    tool = Tool(
        name="secret",
        description="Return one secret without loss.",
        input_type=IntegerValue,
        output_type=SecretValue,
        shared_service=service,
    )
    agent, _driver = create_integer_agent(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="secret-result",
                        name="secret",
                        arguments={"value": 1},
                    )
                ]
            )
        ],
        tools=[tool],
    )

    with pytest.raises(AgentToolOutputValidationError):
        await agent.execute({"value": 1}, dependencies=None)

    tool_span = next(
        span
        for span in span_exporter.get_finished_spans()
        if span.attributes.get("junjo.agent.operation_type") == "tool"
    )
    assert tool_span.attributes["junjo.agent.tool.result_candidate.available"] is False
    assert tool_span.attributes["junjo.agent.tool.result_candidate.unavailable_reason"] == "not_json_serializable"


@pytest.mark.asyncio
async def test_typed_python_value_cannot_project_into_an_unrelated_string_boundary() -> None:
    driver = ScriptedModelDriver([FinalOutputResponse(output={"value": 1})])
    agent = Agent(
        key="string_agent",
        name="String Agent",
        instructions="Require a real string.",
        input_type=str,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=(),
        output_type=IntegerValue,
    )

    with pytest.raises(AgentInputValidationError):
        await agent.execute(Path("projected-string"), dependencies=None)

    assert driver.requests == ()


@pytest.mark.asyncio
async def test_declared_json_format_preserves_raw_and_typed_values() -> None:
    driver = ScriptedModelDriver(
        [
            FinalOutputResponse(output={"value": 1}),
            FinalOutputResponse(output={"value": 2}),
        ]
    )
    agent = Agent(
        key="datetime_agent",
        name="Datetime Agent",
        instructions="Accept only the declared date-time format.",
        input_type=DatetimeValue,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=(),
        output_type=IntegerValue,
    )

    raw_result = await agent.execute(
        {"value": "2026-07-14T12:30:00"},
        dependencies=None,
    )
    typed_result = await agent.execute(
        DatetimeValue(value=datetime(2026, 7, 14, 12, 30)),
        dependencies=None,
    )

    assert raw_result.output.value == 1
    assert typed_result.output.value == 2
