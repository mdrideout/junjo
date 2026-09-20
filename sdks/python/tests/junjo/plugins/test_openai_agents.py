import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agents import Agent
from agents.testing import ScriptedModel, assistant_message
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel, ConfigDict

from junjo import Agent as JunjoAgent
from junjo import BaseState, BaseStore, ModelDriverBinding, ModelDriverDescriptor
from junjo.agent import FinalOutputResponse
from junjo.agent.testing import ScriptedModelDriver
from junjo.evaluation import EvaluationContext, EvaluationRunClass, ExecutionServiceIdentity
from junjo.plugins.openai_agents import (
    AgentToolInvocation,
    WorkflowToolInvocation,
    agent_as_tool,
    instrument_openai_agents,
    workflow_as_tool,
)
from junjo.plugins.openai_agents.evaluation import OpenAIAgentInvocation, OpenAIAgentTarget


class ExampleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str


@pytest.mark.asyncio
@pytest.mark.parametrize("borrowed", [False, True])
async def test_workflow_as_tool_validates_input_and_projects_output(borrowed: bool) -> None:
    workflow = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(state={"answer": "Brooklyn"})))
    store = BaseStore(BaseState()) if borrowed else None
    tool = workflow_as_tool(
        name="find_local_place",
        description="Find one local place.",
        input_type=ExampleInput,
        workflow_factory=lambda _input: WorkflowToolInvocation(workflow=workflow, store=store),  # type: ignore[arg-type]
        output_projector=lambda result, _input: result.state["answer"],
    )

    output = await tool.on_invoke_tool(None, '{"message":"Where should I go?"}')  # type: ignore[arg-type]

    assert output == "Brooklyn"
    workflow.execute.assert_awaited_once_with(store=store, correlation=None)
    assert tool.params_json_schema["additionalProperties"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("borrowed", [False, True])
async def test_agent_as_tool_preserves_application_store_choice(borrowed: bool) -> None:
    class State(BaseState):
        message: str

    store = BaseStore(State(message="borrowed")) if borrowed else None
    definition = JunjoAgent[ExampleInput, ExampleInput, None, State, BaseStore[State]](
        key="native",
        name="Native Agent",
        instructions="Return one message.",
        input_type=ExampleInput,
        output_type=ExampleInput,
        tools=(),
        store_factory=lambda: BaseStore(State(message="factory")),
        model=ModelDriverBinding.per_run(
            descriptor=ModelDriverDescriptor(driver_key="scripted", provider="junjo", model="fixture"),
            factory=lambda: ScriptedModelDriver([FinalOutputResponse(output={"message": "done"})]),
        ),
    )
    tool = agent_as_tool(
        name="native",
        description="Run the native Agent.",
        input_type=ExampleInput,
        agent_factory=lambda value: AgentToolInvocation(
            agent=definition,
            input=value,
            dependencies=None,
            store=store,
        ),
        output_projector=lambda result, _input: result.application_state.message,
    )
    assert await tool.on_invoke_tool(None, '{"message":"run"}') == ("borrowed" if borrowed else "factory")


@pytest.mark.asyncio
async def test_openai_agent_target_returns_exact_invoke_agent_span_evidence() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.namespace": "junjo.examples",
                "service.name": "base-openai-agents",
            }
        )
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    integration = instrument_openai_agents(tracer_provider=provider)
    model = ScriptedModel([[assistant_message("A realistic local answer.")]])
    agent = Agent(name="OpenAI coordinator", model=model)
    target = OpenAIAgentTarget[
        ExampleInput,
        None,
        None,
    ](
        key="openai_coordinator",
        name="OpenAI coordinator",
        input_version=1,
        input_type=ExampleInput,
        expected_agent_name="OpenAI coordinator",
        factory=lambda input_value, _context, _resources: OpenAIAgentInvocation(
            agent=agent,
            input=input_value.message,
        ),
        projector=lambda result, _input, _context, _resources: result.final_output,
    )

    try:
        result = await target.execute(
            ExampleInput(message="Recommend somewhere local."),
            context=EvaluationContext(
                run_class=EvaluationRunClass.EVALUATION,
                dataset_id="dataset",
                run_id="run",
                case_id="case",
                attempt_id="attempt",
                source_revision="1" * 40,
            ),
            service_identity=ExecutionServiceIdentity(
                service_namespace="junjo.examples",
                service_name="base-openai-agents",
            ),
            resources=None,
        )
        provider.force_flush()
    finally:
        integration.close()
        provider.shutdown()

    assert result.subject == "A realistic local answer."
    assert result.evidence.kind == "otel_span"
    assert result.evidence.service_namespace == "junjo.examples"
    assert result.evidence.service_name == "base-openai-agents"
    spans = exporter.get_finished_spans()
    matching = [
        span
        for span in spans
        if span.attributes.get("gen_ai.operation.name") == "invoke_agent"
        and span.attributes.get("gen_ai.agent.name") == "OpenAI coordinator"
    ]
    assert len(matching) == 1
    assert result.evidence.trace_id == format(matching[0].context.trace_id, "032x")
    assert result.evidence.span_id == format(matching[0].context.span_id, "016x")


@pytest.mark.asyncio
async def test_concurrent_openai_agent_targets_capture_only_their_task_local_evidence() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.namespace": "junjo.examples",
                "service.name": "base-openai-agents",
            }
        )
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    integration = instrument_openai_agents(tracer_provider=provider)

    def invocation(
        input_value: ExampleInput,
        _context: EvaluationContext,
        _resources: None,
    ) -> OpenAIAgentInvocation[None]:
        model = ScriptedModel([[assistant_message(f"Response for {input_value.message}")]])
        return OpenAIAgentInvocation(
            agent=Agent(name="Shared coordinator", model=model),
            input=input_value.message,
        )

    target = OpenAIAgentTarget[ExampleInput, None, None](
        key="shared_coordinator",
        name="Shared coordinator",
        input_version=1,
        input_type=ExampleInput,
        expected_agent_name="Shared coordinator",
        factory=invocation,
        projector=lambda result, _input, _context, _resources: result.final_output,
    )

    def context(case_id: str) -> EvaluationContext:
        return EvaluationContext(
            run_class=EvaluationRunClass.EVALUATION,
            dataset_id="dataset",
            run_id="run",
            case_id=case_id,
            attempt_id=f"attempt-{case_id}",
            source_revision="1" * 40,
        )

    service_identity = ExecutionServiceIdentity(
        service_namespace="junjo.examples",
        service_name="base-openai-agents",
    )
    try:
        first, second = await asyncio.gather(
            target.execute(
                ExampleInput(message="first"),
                context=context("first"),
                service_identity=service_identity,
                resources=None,
            ),
            target.execute(
                ExampleInput(message="second"),
                context=context("second"),
                service_identity=service_identity,
                resources=None,
            ),
        )
        provider.force_flush()
    finally:
        integration.close()
        provider.shutdown()

    assert first.subject == "Response for first"
    assert second.subject == "Response for second"
    assert first.evidence.trace_id != second.evidence.trace_id
    assert first.evidence.span_id != second.evidence.span_id
    emitted_references = {
        (
            format(span.context.trace_id, "032x"),
            format(span.context.span_id, "016x"),
        )
        for span in exporter.get_finished_spans()
        if span.attributes.get("gen_ai.operation.name") == "invoke_agent"
        and span.attributes.get("gen_ai.agent.name") == "Shared coordinator"
    }
    assert {
        (first.evidence.trace_id, first.evidence.span_id),
        (second.evidence.trace_id, second.evidence.span_id),
    } == emitted_references
