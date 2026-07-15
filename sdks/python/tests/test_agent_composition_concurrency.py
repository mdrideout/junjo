from __future__ import annotations

import asyncio
import json

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from junjo import (
    Agent,
    AgentLimits,
    BaseState,
    BaseStore,
    ExecutionCorrelation,
    Graph,
    Hooks,
    ModelDriverBinding,
    ModelDriverDescriptor,
    Node,
    Tool,
    Workflow,
    WorkflowExecutionError,
)
from junjo.agent import (
    AgentExecutionResult,
    AgentLimitExceededError,
    AgentModelError,
    AgentToolError,
    FinalOutputResponse,
    ToolCall,
    ToolCallsResponse,
)
from junjo.agent.testing import ScriptedError, ScriptedModelDriver


class AgentInput(BaseModel):
    value: str


class AgentOutput(BaseModel):
    value: str


def descriptor() -> ModelDriverDescriptor:
    return ModelDriverDescriptor(
        driver_key="scripted",
        provider="junjo",
        model="scripted-v1",
    )


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)
    return exporter


class ParentState(BaseState):
    input: str
    answer: str | None = None


class ParentStore(BaseStore[ParentState]):
    async def set_answer(self, value: str) -> None:
        await self.set_state({"answer": value})


class ExecuteAgentNode(Node[ParentStore]):
    def __init__(
        self,
        agent: Agent,
        results: list[AgentExecutionResult] | None = None,
    ) -> None:
        super().__init__()
        self.agent = agent
        self.results = results

    async def service(self, store: ParentStore) -> None:
        state = await store.get_state()
        result = await self.agent.execute(
            AgentInput(value=state.input),
            dependencies=None,
        )
        if self.results is not None:
            self.results.append(result)
        await store.set_answer(result.output.value)


class ConflictingCorrelationNode(Node[ParentStore]):
    def __init__(self, agent: Agent) -> None:
        super().__init__()
        self.agent = agent

    async def service(self, store: ParentStore) -> None:
        state = await store.get_state()
        await self.agent.execute(
            AgentInput(value=state.input),
            dependencies=None,
            correlation=ExecutionCorrelation(type="test.turn", id="replacement"),
        )


@pytest.mark.asyncio
async def test_workflow_node_invokes_agent_with_truthful_semantic_parent(
    span_exporter: InMemorySpanExporter,
) -> None:
    async def echo_service(input: AgentInput, context) -> AgentOutput:
        return AgentOutput(value=input.value)

    tool = Tool(
        name="echo",
        description="Echo one value.",
        input_type=AgentInput,
        output_type=AgentOutput,
        shared_service=echo_service,
    )
    driver = ScriptedModelDriver(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="nested-echo",
                        name="echo",
                        arguments={"value": "from tool"},
                    )
                ]
            ),
            FinalOutputResponse(output={"value": "from agent"}),
        ]
    )
    agent_hooks = Hooks()
    workflow_hooks = Hooks()
    agent_store_ids: list[str] = []
    workflow_store_ids: list[str] = []
    agent_hooks.on_agent_started(lambda event: agent_store_ids.append(event.store_id))
    workflow_hooks.on_workflow_started(
        lambda event: workflow_store_ids.append(event.store_id)
    )
    agent = Agent(
        key="nested_agent",
        name="Nested Agent",
        instructions="Answer.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(descriptor=descriptor(), driver=driver),
        tools=[tool],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=2, tool_calls=1),
        hooks=agent_hooks,
    )
    nodes: list[ExecuteAgentNode] = []
    agent_results: list[AgentExecutionResult] = []

    def graph_factory() -> Graph:
        node = ExecuteAgentNode(agent, agent_results)
        nodes.append(node)
        return Graph(source=node, sinks=[node], edges=[])

    workflow = Workflow(
        name="Agent Parent Workflow",
        graph_factory=graph_factory,
        store_factory=lambda: ParentStore(ParentState(input="question")),
        max_iterations=1,
        hooks=workflow_hooks,
    )

    result = await workflow.execute(
        correlation=ExecutionCorrelation(type="test.turn", id="turn-1")
    )

    assert result.state.answer == "from agent"
    assert agent_results[0].output.value == "from agent"
    assert agent_results[0].model_request_count == 2
    assert agent_results[0].tool_call_completed_count == 1
    assert result.node_execution_counts[nodes[0].id] == 1
    assert agent_store_ids[0] != workflow_store_ids[0]
    agent_results[0].output.value = "mutated child result"
    assert result.state.answer == "from agent"
    spans = span_exporter.get_finished_spans()
    node_span = next(span for span in spans if span.name == "ExecuteAgentNode")
    agent_span = next(span for span in spans if span.name == "Nested Agent")
    assert agent_span.parent.span_id == node_span.context.span_id
    assert agent_span.attributes["junjo.parent_executable_definition_id"] == nodes[0].id
    assert agent_span.attributes["junjo.parent_executable_type"] == "node"
    assert "junjo.enclosing_graph_structural_id" not in agent_span.attributes
    owner_spans = [
        span
        for span in spans
        if span.attributes.get("junjo.span_type") in {"workflow", "node", "agent"}
    ]
    assert owner_spans
    for owner_span in owner_spans:
        assert owner_span.attributes["junjo.correlation.type"] == "test.turn"
        assert owner_span.attributes["junjo.correlation.id"] == "turn-1"
    operation_spans = [
        span
        for span in spans
        if "junjo.agent.operation_type" in span.attributes
    ]
    assert operation_spans
    for operation_span in operation_spans:
        assert "junjo.correlation.type" not in operation_span.attributes
        assert "junjo.correlation.id" not in operation_span.attributes


@pytest.mark.asyncio
async def test_nested_executable_cannot_replace_active_correlation() -> None:
    agent = Agent(
        key="conflicting_agent",
        name="Conflicting Agent",
        instructions="Do not run.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=descriptor(),
            driver=ScriptedModelDriver(
                [FinalOutputResponse(output={"value": "unused"})]
            ),
        ),
        tools=[],
        output_type=AgentOutput,
    )

    def graph_factory() -> Graph:
        node = ConflictingCorrelationNode(agent)
        return Graph(source=node, sinks=[node], edges=[])

    workflow = Workflow(
        name="Correlation Parent Workflow",
        graph_factory=graph_factory,
        store_factory=lambda: ParentStore(ParentState(input="question")),
        max_iterations=1,
    )

    with pytest.raises(WorkflowExecutionError) as raised:
        await workflow.execute(
            correlation=ExecutionCorrelation(type="test.turn", id="original")
        )
    assert isinstance(raised.value.__cause__, ValueError)
    assert "cannot replace the active correlation" in str(raised.value.__cause__)


class ChildState(BaseState):
    value: str


class ChildStore(BaseStore[ChildState]):
    async def uppercase(self) -> None:
        state = await self.get_state()
        await self.set_state({"value": state.value.upper()})


class UppercaseNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        await store.uppercase()


def _uppercase_graph() -> Graph:
    node = UppercaseNode()
    return Graph(source=node, sinks=[node], edges=[])


class WorkflowToolInput(BaseModel):
    value: str


class WorkflowToolOutput(BaseModel):
    value: str


class ExecuteInnerAgentNode(Node[ChildStore]):
    def __init__(self, agent: Agent, results: list[AgentExecutionResult]) -> None:
        super().__init__()
        self.agent = agent
        self.results = results

    async def service(self, store: ChildStore) -> None:
        state = await store.get_state()
        result = await self.agent.execute(
            AgentInput(value=state.value),
            dependencies=None,
        )
        self.results.append(result)
        await store.set_state({"value": result.output.value})


@pytest.mark.asyncio
async def test_agent_tool_invokes_fresh_workflow_with_agent_semantic_parent(
    span_exporter: InMemorySpanExporter,
) -> None:
    child_results = []
    child_store_ids: list[str] = []
    child_definitions: list[Workflow] = []
    child_hooks = Hooks()
    agent_hooks = Hooks()
    agent_store_ids: list[str] = []
    child_hooks.on_workflow_started(
        lambda event: child_store_ids.append(event.store_id)
    )
    agent_hooks.on_agent_started(lambda event: agent_store_ids.append(event.store_id))

    async def workflow_service(input: WorkflowToolInput, context) -> WorkflowToolOutput:
        workflow = Workflow(
            name="Tool Child Workflow",
            graph_factory=_uppercase_graph,
            store_factory=lambda: ChildStore(ChildState(value=input.value)),
            max_iterations=1,
            hooks=child_hooks,
        )
        child_definitions.append(workflow)
        child_result = await workflow.execute()
        child_results.append(child_result)
        return WorkflowToolOutput(value=child_result.state.value)

    tool = Tool(
        name="run_workflow",
        description="Run a fresh child Workflow.",
        input_type=WorkflowToolInput,
        output_type=WorkflowToolOutput,
        shared_service=workflow_service,
    )
    driver = ScriptedModelDriver(
        [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="workflow-call",
                        name="run_workflow",
                        arguments={"value": "child"},
                    )
                ]
            ),
            FinalOutputResponse(output={"value": "CHILD"}),
        ]
    )
    agent = Agent(
        key="workflow_agent",
        name="Workflow Agent",
        instructions="Use the workflow Tool.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(descriptor=descriptor(), driver=driver),
        tools=[tool],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=2, tool_calls=1),
        hooks=agent_hooks,
    )

    result = await agent.execute(AgentInput(value="child"), dependencies=None)

    assert result.output.value == "CHILD"
    assert result.model_request_count == 2
    assert result.tool_call_completed_count == 1
    assert child_results[0].state.value == "CHILD"
    assert next(iter(child_results[0].node_execution_counts.values())) == 1
    assert agent_store_ids[0] != child_store_ids[0]
    assert child_results[0].definition_id == child_definitions[0].id
    child_results[0].state.value = "mutated workflow result"
    assert result.output.value == "CHILD"
    spans = span_exporter.get_finished_spans()
    agent_span = next(span for span in spans if span.name == "Workflow Agent")
    tool_span = next(
        span for span in spans if span.attributes.get("junjo.agent.operation_type") == "tool"
    )
    workflow_span = next(span for span in spans if span.name == "Tool Child Workflow")
    assert workflow_span.parent.span_id == tool_span.context.span_id
    assert tool_span.parent.span_id == agent_span.context.span_id
    assert workflow_span.attributes["junjo.parent_executable_definition_id"] == agent.definition_id
    assert workflow_span.attributes["junjo.parent_executable_runtime_id"] == result.run_id
    assert workflow_span.attributes["junjo.parent_executable_type"] == "agent"
    assert "junjo.workflow.execution_graph_snapshot" in workflow_span.attributes


@pytest.mark.asyncio
async def test_nested_agent_owner_sequences_restart_inside_workflow_tool(
    span_exporter: InMemorySpanExporter,
) -> None:
    inner_results: list[AgentExecutionResult] = []
    workflow_results = []
    inner = Agent(
        key="inner_owner_agent",
        name="Inner Owner Agent",
        instructions="Complete inside the nested Node.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=descriptor(),
            driver=ScriptedModelDriver(
                [FinalOutputResponse(output={"value": "inner result"})]
            ),
        ),
        tools=[],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=1, tool_calls=1),
    )

    async def nested_service(
        input: WorkflowToolInput,
        context,
    ) -> WorkflowToolOutput:
        def graph_factory() -> Graph:
            node = ExecuteInnerAgentNode(inner, inner_results)
            return Graph(source=node, sinks=[node], edges=[])

        workflow = Workflow(
            name="Nested Owner Workflow",
            graph_factory=graph_factory,
            store_factory=lambda: ChildStore(ChildState(value=input.value)),
            max_iterations=1,
        )
        result = await workflow.execute()
        workflow_results.append(result)
        return WorkflowToolOutput(value=result.state.value)

    tool = Tool(
        name="nested_owner_workflow",
        description="Run a Workflow whose Node executes another Agent.",
        input_type=WorkflowToolInput,
        output_type=WorkflowToolOutput,
        shared_service=nested_service,
    )
    outer = Agent(
        key="outer_owner_agent",
        name="Outer Owner Agent",
        instructions="Call the nested Workflow.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=descriptor(),
            driver=ScriptedModelDriver(
                [
                    ToolCallsResponse(
                        tool_calls=[
                            ToolCall(
                                id="nested-owner",
                                name="nested_owner_workflow",
                                arguments={"value": "start"},
                            )
                        ]
                    ),
                    FinalOutputResponse(output={"value": "inner result"}),
                ]
            ),
        ),
        tools=[tool],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=2, tool_calls=1),
    )

    outer_result = await outer.execute(AgentInput(value="start"), dependencies=None)

    assert outer_result.output.value == "inner result"
    assert inner_results[0].output.value == "inner result"
    assert workflow_results[0].state.value == "inner result"
    spans = span_exporter.get_finished_spans()
    outer_span = next(span for span in spans if span.name == "Outer Owner Agent")
    tool_span = next(
        span for span in spans if span.attributes.get("junjo.agent.operation_type") == "tool"
    )
    workflow_span = next(span for span in spans if span.name == "Nested Owner Workflow")
    node_span = next(span for span in spans if span.name == "ExecuteInnerAgentNode")
    inner_span = next(span for span in spans if span.name == "Inner Owner Agent")
    assert tool_span.parent.span_id == outer_span.context.span_id
    assert workflow_span.parent.span_id == tool_span.context.span_id
    assert node_span.parent.span_id == workflow_span.context.span_id
    assert inner_span.parent.span_id == node_span.context.span_id
    assert workflow_span.attributes["junjo.parent_executable_runtime_id"] == outer_result.run_id
    assert inner_span.attributes["junjo.parent_executable_runtime_id"] == node_span.attributes[
        "junjo.executable_runtime_id"
    ]
    assert len(
        {
            outer_span.attributes["junjo.agent.store.id"],
            inner_span.attributes["junjo.agent.store.id"],
            workflow_span.attributes["junjo.workflow.store.id"],
        }
    ) == 3
    owners = (outer_span, inner_span)
    expected_sequences = {
        outer_result.run_id: [1, 2, 3],
        inner_results[0].run_id: [1],
    }
    for owner in owners:
        runtime_id = owner.attributes["junjo.agent.runtime_id"]
        sequences = sorted(
            span.attributes["junjo.agent.operation.sequence"]
            for span in spans
            if span.attributes.get("junjo.agent.runtime_id") == runtime_id
            and "junjo.agent.operation_type" in span.attributes
        )
        assert sequences == expected_sequences[runtime_id]


@pytest.mark.asyncio
async def test_workflow_and_nested_agent_enforce_their_own_limits(
    span_exporter: InMemorySpanExporter,
) -> None:
    async def echo(input: AgentInput, context) -> AgentOutput:
        return AgentOutput(value=input.value)

    tool = Tool(
        name="echo_for_limit",
        description="Use the only admitted Tool call.",
        input_type=AgentInput,
        output_type=AgentOutput,
        shared_service=echo,
    )
    agent = Agent(
        key="nested_limit_agent",
        name="Nested Limit Agent",
        instructions="Exhaust the model budget.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=descriptor(),
            driver=ScriptedModelDriver(
                [
                    ToolCallsResponse(
                        tool_calls=[
                            ToolCall(
                                id="limit-echo",
                                name="echo_for_limit",
                                arguments={"value": "x"},
                            )
                        ]
                    )
                ]
            ),
        ),
        tools=[tool],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=1, tool_calls=1),
    )
    workflow = Workflow(
        name="Independent Workflow Limit",
        graph_factory=lambda: _agent_node_graph(agent),
        store_factory=lambda: ParentStore(ParentState(input="x")),
        max_iterations=7,
    )

    with pytest.raises(WorkflowExecutionError) as raised:
        await workflow.execute()

    agent_error = raised.value.__cause__
    assert isinstance(agent_error, AgentLimitExceededError)
    assert agent_error.limit_kind == "model_requests"
    assert agent_error.limit == 1
    assert agent_error.state.model_request_count == 1
    assert agent_error.state.tool_call_completed_count == 1
    spans = span_exporter.get_finished_spans()
    agent_span = next(span for span in spans if span.name == "Nested Limit Agent")
    workflow_span = next(
        span for span in spans if span.name == "Independent Workflow Limit"
    )
    assert agent_span.attributes["junjo.agent.limit.exceeded"] == "model_requests"
    assert workflow_span.status.status_code.name == "ERROR"
    assert "junjo.agent.limit.exceeded" not in workflow_span.attributes


@pytest.mark.asyncio
async def test_agent_and_workflow_tool_enforce_their_own_limits(
    span_exporter: InMemorySpanExporter,
) -> None:
    async def limited_workflow_service(
        input: WorkflowToolInput,
        context,
    ) -> WorkflowToolOutput:
        workflow = Workflow(
            name="Iteration Limited Child",
            graph_factory=_uppercase_graph,
            store_factory=lambda: ChildStore(ChildState(value=input.value)),
            max_iterations=0,
        )
        child_result = await workflow.execute()
        return WorkflowToolOutput(value=child_result.state.value)

    tool = Tool(
        name="limited_workflow",
        description="Run a Workflow with its own zero-iteration bound.",
        input_type=WorkflowToolInput,
        output_type=WorkflowToolOutput,
        shared_service=limited_workflow_service,
    )
    agent = Agent(
        key="workflow_limit_agent",
        name="Workflow Limit Agent",
        instructions="Call the limited Workflow.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=descriptor(),
            driver=ScriptedModelDriver(
                [
                    ToolCallsResponse(
                        tool_calls=[
                            ToolCall(
                                id="limited-workflow",
                                name="limited_workflow",
                                arguments={"value": "child"},
                            )
                        ]
                    )
                ]
            ),
        ),
        tools=[tool],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=3, tool_calls=2),
    )

    with pytest.raises(AgentToolError) as raised:
        await agent.execute(AgentInput(value="child"), dependencies=None)

    workflow_error = raised.value.__cause__
    assert isinstance(workflow_error, WorkflowExecutionError)
    assert isinstance(workflow_error.__cause__, ValueError)
    assert "exceeded maximum execution count" in str(workflow_error.__cause__)
    assert raised.value.state.model_request_count == 1
    assert raised.value.state.tool_call_admitted_count == 1
    assert raised.value.state.tool_call_started_count == 1
    assert raised.value.state.tool_call_completed_count == 0
    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.name == "Workflow Limit Agent")
    child = next(span for span in spans if span.name == "Iteration Limited Child")
    child_state = json.loads(child.attributes["junjo.workflow.state.end"])
    assert "junjo.agent.limit.exceeded" not in owner.attributes
    assert child_state["value"] == "CHILD"
    assert child.status.status_code.name == "ERROR"


def _agent_node_graph(agent: Agent) -> Graph:
    node = ExecuteAgentNode(agent)
    return Graph(source=node, sinks=[node], edges=[])


@pytest.mark.asyncio
async def test_reusable_agent_concurrent_runs_isolate_factories_state_and_results() -> None:
    entered = 0
    all_entered = asyncio.Event()
    factory_count = 0

    class EchoDriver:
        async def request(self, request):
            nonlocal entered
            entered += 1
            if entered == 2:
                all_entered.set()
            await all_entered.wait()
            input_message = request.to_json()["messages"][-1]
            return FinalOutputResponse(output={"value": input_message["input"]["value"]})

    def driver_factory() -> EchoDriver:
        nonlocal factory_count
        factory_count += 1
        return EchoDriver()

    agent = Agent(
        key="concurrent_agent",
        name="Concurrent Agent",
        instructions="Echo input.",
        input_type=AgentInput,
        model=ModelDriverBinding.per_run(descriptor=descriptor(), factory=driver_factory),
        tools=[],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=2, tool_calls=2),
    )

    first, second = await asyncio.gather(
        agent.execute(AgentInput(value="first"), dependencies=None),
        agent.execute(AgentInput(value="second"), dependencies=None),
    )

    assert factory_count == 2
    assert first.run_id != second.run_id
    assert first.output.value == "first"
    assert second.output.value == "second"
    first.output.value = "caller mutation"
    assert second.output.value == "second"


@pytest.mark.asyncio
async def test_one_agent_concurrently_uses_reusable_and_per_call_workflow_definitions() -> None:  # noqa: C901
    tool_entered = 0
    all_tools_entered = asyncio.Event()
    reusable_graph_factories = 0
    reusable_store_factories = 0
    per_call_workflow_factories = 0
    driver_factories = 0
    child_store_ids: list[str] = []
    agent_store_ids: list[str] = []
    reusable_results = []
    per_call_results = []
    per_call_definitions: list[Workflow] = []
    child_hooks = Hooks()
    agent_hooks = Hooks()
    child_hooks.on_workflow_started(
        lambda event: child_store_ids.append(event.store_id)
    )
    agent_hooks.on_agent_started(lambda event: agent_store_ids.append(event.store_id))

    def reusable_graph_factory() -> Graph:
        nonlocal reusable_graph_factories
        reusable_graph_factories += 1
        return _uppercase_graph()

    def reusable_store_factory() -> ChildStore:
        nonlocal reusable_store_factories
        reusable_store_factories += 1
        return ChildStore(ChildState(value="reusable"))

    reusable_workflow = Workflow(
        name="Eligible Reusable Workflow",
        graph_factory=reusable_graph_factory,
        store_factory=reusable_store_factory,
        max_iterations=1,
        hooks=child_hooks,
    )

    async def wait_for_all_tools() -> None:
        nonlocal tool_entered
        tool_entered += 1
        if tool_entered == 3:
            all_tools_entered.set()
        await all_tools_entered.wait()

    async def reusable_service(
        input: WorkflowToolInput,
        context,
    ) -> WorkflowToolOutput:
        await wait_for_all_tools()
        result = await reusable_workflow.execute()
        reusable_results.append(result)
        return WorkflowToolOutput(value=result.state.value)

    def create_per_call_workflow(value: str) -> Workflow:
        nonlocal per_call_workflow_factories
        per_call_workflow_factories += 1
        workflow = Workflow(
            name="Per Call Workflow",
            graph_factory=_uppercase_graph,
            store_factory=lambda: ChildStore(ChildState(value=value)),
            max_iterations=1,
            hooks=child_hooks,
        )
        per_call_definitions.append(workflow)
        return workflow

    async def per_call_service(
        input: WorkflowToolInput,
        context,
    ) -> WorkflowToolOutput:
        await wait_for_all_tools()
        workflow = create_per_call_workflow(input.value)
        result = await workflow.execute()
        per_call_results.append(result)
        return WorkflowToolOutput(value=result.state.value)

    reusable_tool = Tool(
        name="reusable_workflow",
        description="Run a definition with no per-call Store data.",
        input_type=WorkflowToolInput,
        output_type=WorkflowToolOutput,
        shared_service=reusable_service,
    )
    per_call_tool = Tool(
        name="per_call_workflow",
        description="Create a definition whose factories close over call data.",
        input_type=WorkflowToolInput,
        output_type=WorkflowToolOutput,
        shared_service=per_call_service,
    )

    class RoutingDriver:
        async def request(self, request):
            messages = request.to_json()["messages"]
            latest = messages[-1]
            if latest["type"] == "agent_input":
                value = latest["input"]["value"]
                tool_name = (
                    "per_call_workflow"
                    if value.startswith("fresh")
                    else "reusable_workflow"
                )
                return ToolCallsResponse(
                    tool_calls=[
                        ToolCall(
                            id=f"{tool_name}-{value}",
                            name=tool_name,
                            arguments={"value": value},
                        )
                    ]
                )
            return FinalOutputResponse(
                output={"value": latest["result"]["value"]}
            )

    def driver_factory() -> RoutingDriver:
        nonlocal driver_factories
        driver_factories += 1
        return RoutingDriver()

    agent = Agent(
        key="mixed_workflow_agent",
        name="Mixed Workflow Agent",
        instructions="Select one Workflow Tool.",
        input_type=AgentInput,
        model=ModelDriverBinding.per_run(
            descriptor=descriptor(),
            factory=driver_factory,
        ),
        tools=[reusable_tool, per_call_tool],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=2, tool_calls=1),
        hooks=agent_hooks,
    )

    first, second, fresh = await asyncio.gather(
        agent.execute(AgentInput(value="reusable-one"), dependencies=None),
        agent.execute(AgentInput(value="reusable-two"), dependencies=None),
        agent.execute(AgentInput(value="fresh-three"), dependencies=None),
    )

    assert [first.output.value, second.output.value, fresh.output.value] == [
        "REUSABLE",
        "REUSABLE",
        "FRESH-THREE",
    ]
    assert driver_factories == 3
    assert reusable_graph_factories == 2
    assert reusable_store_factories == 2
    assert per_call_workflow_factories == 1
    assert len(set(agent_store_ids)) == 3
    assert len(set(child_store_ids)) == 3
    assert set(agent_store_ids).isdisjoint(child_store_ids)
    assert {result.definition_id for result in reusable_results} == {
        reusable_workflow.id
    }
    assert len({result.run_id for result in reusable_results}) == 2
    assert per_call_results[0].definition_id == per_call_definitions[0].id
    assert per_call_definitions[0].id != reusable_workflow.id
    assert all(
        result.model_request_count == 2
        and result.tool_call_completed_count == 1
        for result in (first, second, fresh)
    )
    reusable_results[0].state.value = "caller mutation"
    assert reusable_results[1].state.value == "REUSABLE"
    first.output.value = "caller mutation"
    assert second.output.value == "REUSABLE"


@pytest.mark.asyncio
async def test_shared_hooks_registry_snapshots_workflow_and_agent_runs_independently() -> None:
    hooks = Hooks()
    release_started = asyncio.Event()
    agent_started = asyncio.Event()
    workflow_started = asyncio.Event()
    calls: list[str] = []

    async def block_agent_started(event) -> None:
        agent_started.set()
        await release_started.wait()

    async def block_workflow_started(event) -> None:
        workflow_started.set()
        await release_started.wait()

    hooks.on_agent_started(block_agent_started)
    hooks.on_workflow_started(block_workflow_started)
    unsubscribe_agent = hooks.on_agent_completed(
        lambda event: calls.append("agent-initial")
    )
    unsubscribe_workflow = hooks.on_workflow_completed(
        lambda event: calls.append("workflow-initial")
    )

    class AlwaysFinalDriver:
        async def request(self, request):
            return FinalOutputResponse(output={"value": "agent"})

    agent = Agent(
        key="shared_hooks_agent",
        name="Shared Hooks Agent",
        instructions="Complete.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=descriptor(),
            driver=AlwaysFinalDriver(),
        ),
        tools=[],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=1, tool_calls=1),
        hooks=hooks,
    )
    workflow = Workflow(
        name="Shared Hooks Workflow",
        graph_factory=lambda: _uppercase_graph(),
        store_factory=lambda: ChildStore(ChildState(value="workflow")),
        hooks=hooks,
    )
    agent_task = asyncio.create_task(
        agent.execute(AgentInput(value="agent"), dependencies=None)
    )
    workflow_task = asyncio.create_task(workflow.execute())
    await asyncio.gather(agent_started.wait(), workflow_started.wait())

    unsubscribe_agent()
    unsubscribe_workflow()
    hooks.on_agent_completed(lambda event: calls.append("agent-late"))
    hooks.on_workflow_completed(lambda event: calls.append("workflow-late"))
    release_started.set()
    await asyncio.gather(agent_task, workflow_task)

    assert sorted(calls) == ["agent-initial", "workflow-initial"]
    calls.clear()
    await asyncio.gather(
        agent.execute(AgentInput(value="agent"), dependencies=None),
        workflow.execute(),
    )
    assert sorted(calls) == ["agent-late", "workflow-late"]


@pytest.mark.asyncio
async def test_agent_failure_propagates_through_node_and_workflow_with_owned_spans(
    span_exporter: InMemorySpanExporter,
) -> None:
    cause = RuntimeError("model failed")
    agent = Agent(
        key="failing_nested_agent",
        name="Failing Nested Agent",
        instructions="Fail.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=descriptor(),
            driver=ScriptedModelDriver([ScriptedError(cause)]),
        ),
        tools=[],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=1, tool_calls=1),
    )

    def graph_factory() -> Graph:
        node = ExecuteAgentNode(agent)
        return Graph(source=node, sinks=[node], edges=[])

    workflow = Workflow(
        name="Failing Parent Workflow",
        graph_factory=graph_factory,
        store_factory=lambda: ParentStore(ParentState(input="question")),
        max_iterations=7,
    )

    with pytest.raises(WorkflowExecutionError) as raised:
        await workflow.execute()

    agent_error = raised.value.__cause__
    assert isinstance(agent_error, AgentModelError)
    assert agent_error.__cause__ is cause
    spans = span_exporter.get_finished_spans()
    assert next(span for span in spans if span.name == "Failing Nested Agent").status.status_code.name == "ERROR"
    assert next(span for span in spans if span.name == "ExecuteAgentNode").status.status_code.name == "ERROR"
    assert next(span for span in spans if span.name == "Failing Parent Workflow").status.status_code.name == "ERROR"


class FailingChildNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        raise RuntimeError("child workflow failed")


@pytest.mark.asyncio
async def test_nested_workflow_failure_becomes_tool_error_with_original_cause(
    span_exporter: InMemorySpanExporter,
) -> None:
    async def workflow_service(input: WorkflowToolInput, context) -> WorkflowToolOutput:
        def graph_factory() -> Graph:
            node = FailingChildNode()
            return Graph(source=node, sinks=[node], edges=[])

        workflow = Workflow(
            name="Failing Child Workflow",
            graph_factory=graph_factory,
            store_factory=lambda: ChildStore(ChildState(value=input.value)),
            max_iterations=99,
        )
        result = await workflow.execute()
        return WorkflowToolOutput(value=result.state.value)

    tool = Tool(
        name="failing_workflow",
        description="Run a failing Workflow.",
        input_type=WorkflowToolInput,
        output_type=WorkflowToolOutput,
        shared_service=workflow_service,
    )
    agent = Agent(
        key="workflow_failure_agent",
        name="Workflow Failure Agent",
        instructions="Call the Tool.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=descriptor(),
            driver=ScriptedModelDriver(
                [
                    ToolCallsResponse(
                        tool_calls=[
                            ToolCall(
                                id="failing-workflow",
                                name="failing_workflow",
                                arguments={"value": "x"},
                            )
                        ]
                    )
                ]
            ),
        ),
        tools=[tool],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=2, tool_calls=1),
    )

    with pytest.raises(AgentToolError) as raised:
        await agent.execute(AgentInput(value="x"), dependencies=None)

    workflow_error = raised.value.__cause__
    assert isinstance(workflow_error, WorkflowExecutionError)
    assert isinstance(workflow_error.__cause__, RuntimeError)
    assert str(workflow_error.__cause__) == "child workflow failed"
    spans = span_exporter.get_finished_spans()
    assert next(span for span in spans if span.name == "Failing Child Workflow").status.status_code.name == "ERROR"
    tool_span = next(
        span for span in spans if span.attributes.get("junjo.agent.operation_type") == "tool"
    )
    assert tool_span.status.status_code.name == "ERROR"


@pytest.mark.asyncio
async def test_cancellation_propagates_workflow_node_agent_without_surviving_work(
    span_exporter: InMemorySpanExporter,
) -> None:
    entered = asyncio.Event()

    class BlockingDriver:
        async def request(self, request):
            entered.set()
            await asyncio.Event().wait()

    agent = Agent(
        key="cancelled_nested_agent",
        name="Cancelled Nested Agent",
        instructions="Wait.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(descriptor=descriptor(), driver=BlockingDriver()),
        tools=[],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=1, tool_calls=1),
    )

    def graph_factory() -> Graph:
        node = ExecuteAgentNode(agent)
        return Graph(source=node, sinks=[node], edges=[])

    workflow = Workflow(
        name="Cancelled Parent Workflow",
        graph_factory=graph_factory,
        store_factory=lambda: ParentStore(ParentState(input="question")),
    )
    task = asyncio.create_task(workflow.execute())
    await entered.wait()
    task.cancel("cancel hierarchy")
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    spans = span_exporter.get_finished_spans()
    for name in ("Cancelled Nested Agent", "ExecuteAgentNode", "Cancelled Parent Workflow"):
        span = next(item for item in spans if item.name == name)
        assert span.attributes["junjo.cancelled"] is True
        assert span.status.status_code.name == "UNSET"
    assert task.done()


class BlockingChildNode(Node[ChildStore]):
    def __init__(self, entered: asyncio.Event) -> None:
        super().__init__()
        self.entered = entered

    async def service(self, store: ChildStore) -> None:
        self.entered.set()
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_cancellation_propagates_agent_tool_workflow_node_without_surviving_work(
    span_exporter: InMemorySpanExporter,
) -> None:
    entered = asyncio.Event()

    async def workflow_service(input: WorkflowToolInput, context) -> WorkflowToolOutput:
        def graph_factory() -> Graph:
            node = BlockingChildNode(entered)
            return Graph(source=node, sinks=[node], edges=[])

        workflow = Workflow(
            name="Cancelled Child Workflow",
            graph_factory=graph_factory,
            store_factory=lambda: ChildStore(ChildState(value=input.value)),
        )
        result = await workflow.execute()
        return WorkflowToolOutput(value=result.state.value)

    tool = Tool(
        name="blocking_workflow",
        description="Run a blocking Workflow.",
        input_type=WorkflowToolInput,
        output_type=WorkflowToolOutput,
        shared_service=workflow_service,
    )
    agent = Agent(
        key="cancel_workflow_agent",
        name="Cancel Workflow Agent",
        instructions="Call the Tool.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=descriptor(),
            driver=ScriptedModelDriver(
                [
                    ToolCallsResponse(
                        tool_calls=[
                            ToolCall(
                                id="blocking-workflow",
                                name="blocking_workflow",
                                arguments={"value": "x"},
                            )
                        ]
                    )
                ]
            ),
        ),
        tools=[tool],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=2, tool_calls=1),
    )
    task = asyncio.create_task(agent.execute(AgentInput(value="x"), dependencies=None))
    await entered.wait()
    task.cancel("cancel nested workflow")
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    spans = span_exporter.get_finished_spans()
    for name in ("Cancel Workflow Agent", "Cancelled Child Workflow", "BlockingChildNode"):
        span = next(item for item in spans if item.name == name)
        assert span.attributes["junjo.cancelled"] is True
        assert span.status.status_code.name == "UNSET"
    tool_span = next(
        span for span in spans if span.attributes.get("junjo.agent.operation_type") == "tool"
    )
    assert tool_span.attributes["junjo.cancelled"] is True
    assert task.done()


@pytest.mark.asyncio
async def test_agent_cancellation_during_workflow_tool_terminalization_preserves_child_success(
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
) -> None:
    terminal_entered = asyncio.Event()
    release_terminal = asyncio.Event()
    evidence_calls = 0
    original_evidence = ChildStore._get_store_owner_evidence
    child_hooks = Hooks()
    child_lifecycle: list[str] = []
    child_hooks.on_workflow_completed(lambda event: child_lifecycle.append("completed"))

    async def blocked_terminal_evidence(self):
        nonlocal evidence_calls
        evidence_calls += 1
        evidence = await original_evidence(self)
        if evidence_calls == 2:
            terminal_entered.set()
            await release_terminal.wait()
        return evidence

    monkeypatch.setattr(
        ChildStore,
        "_get_store_owner_evidence",
        blocked_terminal_evidence,
    )

    async def workflow_service(input: WorkflowToolInput, context) -> WorkflowToolOutput:
        node = UppercaseNode()
        workflow = Workflow(
            name="Terminal Child Workflow",
            graph_factory=lambda: Graph(source=node, sinks=[node], edges=[]),
            store_factory=lambda: ChildStore(ChildState(value=input.value)),
            hooks=child_hooks,
        )
        result = await workflow.execute()
        return WorkflowToolOutput(value=result.state.value)

    tool = Tool(
        name="terminal_workflow",
        description="Run a child whose final evidence is temporarily blocked.",
        input_type=WorkflowToolInput,
        output_type=WorkflowToolOutput,
        shared_service=workflow_service,
    )
    agent = Agent(
        key="terminal_workflow_agent",
        name="Terminal Workflow Agent",
        instructions="Call the Workflow Tool.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=descriptor(),
            driver=ScriptedModelDriver(
                [
                    ToolCallsResponse(
                        tool_calls=[
                            ToolCall(
                                id="terminal-workflow",
                                name="terminal_workflow",
                                arguments={"value": "child"},
                            )
                        ]
                    )
                ]
            ),
        ),
        tools=[tool],
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=2, tool_calls=1),
    )
    task = asyncio.create_task(agent.execute(AgentInput(value="child"), dependencies=None))
    await terminal_entered.wait()
    task.cancel("cancel while child finalizes")
    await asyncio.sleep(0)
    task.cancel("cancel child finalization again")
    release_terminal.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert child_lifecycle == ["completed"]
    spans = span_exporter.get_finished_spans()
    child = next(span for span in spans if span.name == "Terminal Child Workflow")
    tool_span = next(
        span for span in spans if span.attributes.get("junjo.agent.operation_type") == "tool"
    )
    owner = next(span for span in spans if span.name == "Terminal Workflow Agent")
    assert child.attributes["junjo.store.reconstructable"] is True
    assert "junjo.cancelled" not in child.attributes
    assert child.status.status_code.name == "UNSET"
    assert tool_span.attributes["junjo.cancelled"] is True
    assert owner.attributes["junjo.cancelled"] is True
    assert task.done()
