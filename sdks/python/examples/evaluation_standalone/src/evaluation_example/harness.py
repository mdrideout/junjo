"""Explicit Node, Workflow, and Agent declarations using only public Junjo APIs."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from pydantic import BaseModel, ConfigDict

from junjo import (
    Agent,
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
    EvaluationHarness,
    ExactMatchEvaluator,
    ExecutionServiceIdentity,
    NodeInvocation,
    NodeTarget,
    WorkflowInvocation,
    WorkflowTarget,
)
from junjo.telemetry.junjo_otel_exporter import JunjoOtelExporter

SERVICE_NAMESPACE = "junjo.examples"
SERVICE_NAME = "evaluation-standalone"


@dataclass(frozen=True, slots=True)
class EvaluationExampleRuntime:
    """Process-lifetime telemetry owned by this standalone application."""

    trace_provider: TracerProvider


class NumberInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: int


class NumberOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result: int


class NumberState(BaseState):
    value: int
    result: int | None = None


class NumberStore(BaseStore[NumberState]):
    async def set_result(self, result: int) -> None:
        await self.set_state({"result": result})


class DoubleNode(Node[NumberStore]):
    async def service(self, store: NumberStore) -> None:
        state = await store.get_state()
        await store.set_result(state.value * 2)


def _node_factory(
    input_value: NumberInput,
    context: EvaluationContext,
    resources: EvaluationExampleRuntime,
) -> NodeInvocation[NumberState]:
    del context, resources
    return NodeInvocation(
        node=DoubleNode(),
        store=NumberStore(initial_state=NumberState(value=input_value.value)),
    )


def _state_subject(result, *_context: object) -> int:
    if result.state.result is None:
        raise RuntimeError("The calculation produced no result.")
    return result.state.result


def _workflow_factory(
    input_value: NumberInput,
    context: EvaluationContext,
    resources: EvaluationExampleRuntime,
) -> WorkflowInvocation:
    del context, resources

    def graph() -> Graph:
        node = DoubleNode()
        return Graph(source=node, sinks=[node], edges=[])

    return WorkflowInvocation(
        workflow=Workflow(
            name="Double value",
            graph_factory=graph,
            store_factory=lambda: NumberStore(initial_state=NumberState(value=input_value.value)),
        )
    )


def _agent_factory(
    input_value: NumberInput,
    context: EvaluationContext,
    resources: EvaluationExampleRuntime,
) -> AgentInvocation[NumberInput, NumberOutput, None]:
    del context, resources
    factor = int(os.getenv("JUNJO_EVALUATION_EXAMPLE_AGENT_FACTOR", "2"))
    if factor < 1:
        raise ValueError("JUNJO_EVALUATION_EXAMPLE_AGENT_FACTOR must be positive.")
    driver = ScriptedModelDriver([FinalOutputResponse(output={"result": input_value.value * factor})])
    model = ModelDriverBinding.shared(
        descriptor=ModelDriverDescriptor(
            driver_key="example.scripted",
            provider="junjo",
            model="deterministic",
        ),
        driver=driver,
    )
    return AgentInvocation(
        agent=Agent(
            key="double",
            name="Double value Agent",
            instructions="Return exactly twice the supplied integer.",
            input_type=NumberInput,
            model=model,
            tools=(),
            output_type=NumberOutput,
        ),
        input=input_value,
        dependencies=None,
    )


def _agent_subject(result, *_context: object) -> int:
    return result.output.result


@asynccontextmanager
async def runtime() -> AsyncIterator[EvaluationExampleRuntime]:
    """Install one truthful application telemetry runtime for this process."""

    api_key = os.getenv("JUNJO_AI_STUDIO_API_KEY")
    if api_key is None or not api_key.strip():
        raise ValueError("JUNJO_AI_STUDIO_API_KEY is required for evaluation execution telemetry.")
    exporter = JunjoOtelExporter(
        endpoint=os.getenv("JUNJO_AI_STUDIO_OTLP_ENDPOINT", "localhost:26155"),
        api_key=api_key,
        insecure=_environment_bool("JUNJO_AI_STUDIO_OTLP_INSECURE", default=True),
    )
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.namespace": SERVICE_NAMESPACE,
                "service.name": SERVICE_NAME,
                "service.version": "0.1.0",
            }
        )
    )
    provider.add_span_processor(exporter.span_processor)
    trace.set_tracer_provider(provider)
    if trace.get_tracer_provider() is not provider:
        provider.shutdown()
        raise RuntimeError("OpenTelemetry tracer provider is already installed.")
    try:
        yield EvaluationExampleRuntime(trace_provider=provider)
    finally:
        provider.force_flush()
        provider.shutdown()


def _environment_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{name} must be true or false.")


harness = EvaluationHarness(
    application_key="standalone_evaluation_example",
    service_identity=ExecutionServiceIdentity(
        service_namespace=SERVICE_NAMESPACE,
        service_name=SERVICE_NAME,
    ),
    targets=(
        NodeTarget(
            key="double.node",
            name="Double Number Node",
            input_version=1,
            input_type=NumberInput,
            factory=_node_factory,
            projector=_state_subject,
        ),
        WorkflowTarget(
            key="double.workflow",
            name="Double Number Workflow",
            input_version=1,
            input_type=NumberInput,
            factory=_workflow_factory,
            projector=_state_subject,
        ),
        AgentTarget(
            key="double.agent",
            name="Double Number Agent",
            input_version=1,
            input_type=NumberInput,
            factory=_agent_factory,
            projector=_agent_subject,
        ),
    ),
    evaluators=(ExactMatchEvaluator(),),
    runtime_context=runtime,
)
