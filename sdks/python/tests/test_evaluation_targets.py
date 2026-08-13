"""Real public Node, Workflow, and Agent lifecycle evaluation targets."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from junjo import (
    Agent,
    AgentLimits,
    BaseState,
    BaseStore,
    Graph,
    ModelDriverBinding,
    ModelDriverDescriptor,
    Node,
    Workflow,
)
from junjo.agent import FinalOutputResponse
from junjo.agent.testing import ScriptedModelDriver
from junjo.evaluation import (
    AgentInvocation,
    AgentTarget,
    EvaluationContext,
    EvaluationRole,
    EvaluationRunClass,
    ExecutionServiceIdentity,
    NodeInvocation,
    NodeTarget,
    TargetContractError,
    TargetExecutionError,
    WorkflowInvocation,
    WorkflowTarget,
)
from junjo.studio import ExecutableType

REVISION = "b" * 40


class CaseInput(BaseModel):
    value: str


class ExampleState(BaseState):
    value: str
    output: str | None = None


class ExampleStore(BaseStore[ExampleState]):
    async def set_output(self, value: str) -> None:
        await self.set_state({"output": value})


class UppercaseNode(Node[ExampleStore]):
    async def service(self, store: ExampleStore) -> None:
        state = await store.get_state()
        await store.set_output(state.value.upper())


class FailingNode(Node[ExampleStore]):
    async def service(self, store: ExampleStore) -> None:
        del store
        raise RuntimeError("provider failed")


class AgentInput(BaseModel):
    value: str


class AgentOutput(BaseModel):
    value: str


def _context() -> EvaluationContext:
    return EvaluationContext(
        run_class=EvaluationRunClass.EVALUATION,
        dataset_id="dataset-1",
        run_id="run-1",
        case_id="case-1",
        attempt_id="attempt-1",
        source_revision=REVISION,
        role=EvaluationRole.SUBJECT,
    )


def _service() -> ExecutionServiceIdentity:
    return ExecutionServiceIdentity(
        service_namespace="example.apps",
        service_name="chat",
    )


def _workflow(value: str) -> Workflow[ExampleState, ExampleStore]:
    def graph_factory() -> Graph:
        node = UppercaseNode()
        return Graph(
            source=node,
            sinks=[node],
            edges=[],
        )

    return Workflow(
        name="Example Workflow",
        graph_factory=graph_factory,
        store_factory=lambda: ExampleStore(
            initial_state=ExampleState(value=value)
        ),
    )


def test_target_name_is_explicit_bounded_display_metadata() -> None:
    with pytest.raises(TargetContractError, match="surrounding whitespace"):
        NodeTarget(
            key="uppercase",
            name=" Uppercase Node ",
            input_version=1,
            input_type=CaseInput,
            factory=lambda _input, _context, _resources: None,
            projector=lambda _result, _input, _context, _resources: None,
        )


@pytest.mark.asyncio
async def test_node_target_validates_before_construction_and_uses_evaluate_node() -> None:
    factory_inputs: list[CaseInput] = []

    def factory(
        input_value: CaseInput,
        context: EvaluationContext,
        resources: object,
    ) -> NodeInvocation[ExampleState]:
        assert resources == "shared-runtime"
        assert context.role is EvaluationRole.SUBJECT
        factory_inputs.append(input_value)
        return NodeInvocation(
            node=UppercaseNode(),
            store=ExampleStore(
                initial_state=ExampleState(value=input_value.value)
            ),
        )

    target = NodeTarget(
        key="uppercase",
        name="Uppercase Node",
        input_version=1,
        input_type=CaseInput,
        factory=factory,
        projector=lambda result, _input, _context, _resources: result.state.output,
    )
    with pytest.raises(TargetContractError, match="does not match"):
        target.validate_input({"unknown": "x"})
    assert factory_inputs == []

    result = await target.execute(
        target.validate_input({"value": "hello"}),
        context=_context(),
        service_identity=_service(),
        resources="shared-runtime",
    )

    assert result.subject == "HELLO"
    assert result.execution.service_name == "chat"
    assert result.execution.executable_type is ExecutableType.WORKFLOW
    assert result.execution.runtime_id
    assert factory_inputs == [CaseInput(value="hello")]


@pytest.mark.asyncio
async def test_node_failure_retains_truthful_generated_workflow_identity() -> None:
    cleanups: list[str] = []

    async def cleanup() -> None:
        cleanups.append("node")

    target = NodeTarget(
        key="failing",
        name="Failing Node",
        input_version=1,
        input_type=CaseInput,
        factory=lambda input_value, _context, _resources: NodeInvocation(
            node=FailingNode(),
            store=ExampleStore(
                initial_state=ExampleState(value=input_value.value)
            ),
            cleanup=cleanup,
        ),
        projector=lambda result, _input, _context, _resources: result.state.output,
    )

    with pytest.raises(TargetExecutionError) as raised:
        await target.execute(
            target.validate_input({"value": "hello"}),
            context=_context(),
            service_identity=_service(),
            resources=None,
        )

    assert str(raised.value) == (
        "Node target execution failed: WorkflowExecutionError."
    )
    assert raised.value.execution is not None
    assert raised.value.execution.executable_type is ExecutableType.WORKFLOW
    assert raised.value.execution.runtime_id
    assert cleanups == ["node"]


@pytest.mark.asyncio
async def test_workflow_target_invokes_public_workflow_lifecycle() -> None:
    target = WorkflowTarget(
        key="uppercase-workflow",
        name="Uppercase Workflow",
        input_version=1,
        input_type=CaseInput,
        factory=lambda input_value, _context, _resources: WorkflowInvocation(
            workflow=_workflow(input_value.value)
        ),
        projector=lambda result, _input, _context, _resources: result.state.output,
    )

    result = await target.execute(
        target.validate_input({"value": "workflow"}),
        context=_context(),
        service_identity=_service(),
        resources=None,
    )

    assert result.subject == "WORKFLOW"
    assert result.execution.executable_type is ExecutableType.WORKFLOW


@pytest.mark.asyncio
async def test_workflow_projection_failure_closes_per_case_resources() -> None:
    cleanups: list[str] = []

    async def cleanup() -> None:
        cleanups.append("workflow")

    def fail_projection(
        result: object,
        input_value: CaseInput,
        context: EvaluationContext,
        resources: object,
    ) -> object:
        del result, input_value, context, resources
        raise RuntimeError("projection failed")

    target = WorkflowTarget(
        key="projection-failure",
        name="Projection Failure Workflow",
        input_version=1,
        input_type=CaseInput,
        factory=lambda input_value, _context, _resources: WorkflowInvocation(
            workflow=_workflow(input_value.value),
            cleanup=cleanup,
        ),
        projector=fail_projection,
    )

    with pytest.raises(TargetExecutionError) as raised:
        await target.execute(
            target.validate_input({"value": "workflow"}),
            context=_context(),
            service_identity=_service(),
            resources=None,
        )

    assert str(raised.value) == (
        "Workflow target projection failed: RuntimeError."
    )
    assert raised.value.execution is not None
    assert cleanups == ["workflow"]


@pytest.mark.asyncio
async def test_agent_target_invokes_public_agent_lifecycle() -> None:
    cleanups: list[str] = []

    async def cleanup() -> None:
        cleanups.append("agent")

    driver = ScriptedModelDriver(
        [FinalOutputResponse(output={"value": "agent-output"})]
    )
    agent = Agent(
        key="example-agent",
        name="Example Agent",
        instructions="Return one value.",
        input_type=AgentInput,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=driver,
        ),
        tools=(),
        output_type=AgentOutput,
        limits=AgentLimits(model_requests=1, tool_calls=1),
    )
    target = AgentTarget(
        key="agent",
        name="Example Agent",
        input_version=1,
        input_type=CaseInput,
        factory=lambda input_value, _context, _resources: AgentInvocation(
            agent=agent,
            input=AgentInput(value=input_value.value),
            dependencies=None,
            cleanup=cleanup,
        ),
        projector=lambda result, _input, _context, _resources: result.output.value,
    )

    result = await target.execute(
        target.validate_input({"value": "agent-input"}),
        context=_context(),
        service_identity=_service(),
        resources=None,
    )

    assert result.subject == "agent-output"
    assert result.execution.executable_type is ExecutableType.AGENT
    assert len(driver.requests) == 1
    assert cleanups == ["agent"]
