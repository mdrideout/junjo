"""Studio-controlled evaluation declarations for every example execution scope."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from agents import RunConfig
from junjo.evaluation import (
    AgentInvocation,
    AgentTarget,
    BooleanPredicateEvaluator,
    EvaluationHarness,
    ExecutionServiceIdentity,
    WorkflowInvocation,
    WorkflowTarget,
)
from junjo.plugins.openai_agents.evaluation import OpenAIAgentInvocation, OpenAIAgentTarget
from pydantic import BaseModel, ConfigDict

from .application import (
    JUNJO_AGENT_NAME,
    OPENAI_AGENT_NAME,
    OPENAI_WORKFLOW_NAME,
    WORKFLOW_NAME,
    LocalPlaceInput,
    build_junjo_agent,
    build_openai_agent,
    build_workflow,
)
from .telemetry import SERVICE_NAME, SERVICE_NAMESPACE, TelemetryRuntime, start_telemetry


class ContainsExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str


@asynccontextmanager
async def evaluation_runtime() -> AsyncIterator[TelemetryRuntime]:
    runtime = start_telemetry()
    try:
        yield runtime
    finally:
        runtime.close()


def _contains(subject: object, expectation: ContainsExpectation, *_args: object) -> bool:
    return expectation.text.casefold() in str(subject).casefold()


harness = EvaluationHarness(
    application_key="base_openai_agents",
    service_identity=ExecutionServiceIdentity(
        service_namespace=SERVICE_NAMESPACE,
        service_name=SERVICE_NAME,
    ),
    targets=(
        OpenAIAgentTarget(
            key="openai_local_place_coordinator",
            name=OPENAI_AGENT_NAME,
            input_version=1,
            input_type=LocalPlaceInput,
            expected_agent_name=OPENAI_AGENT_NAME,
            factory=lambda input_value, _context, _resources: OpenAIAgentInvocation(
                agent=build_openai_agent(),
                input=input_value.message,
                run_config=RunConfig(workflow_name=OPENAI_WORKFLOW_NAME),
            ),
            projector=lambda result, _input, _context, _resources: result.final_output,
        ),
        WorkflowTarget(
            key="local_place_workflow",
            name=WORKFLOW_NAME,
            input_version=1,
            input_type=LocalPlaceInput,
            factory=lambda input_value, _context, _resources: WorkflowInvocation(workflow=build_workflow(input_value)),
            projector=lambda result, _input, _context, _resources: result.state.response,
        ),
        AgentTarget(
            key="local_place_agent",
            name=JUNJO_AGENT_NAME,
            input_version=1,
            input_type=LocalPlaceInput,
            factory=lambda input_value, _context, _resources: AgentInvocation(
                agent=build_junjo_agent(input_value),
                input=input_value,
                dependencies=None,
            ),
            projector=lambda result, _input, _context, _resources: result.output.response,
        ),
    ),
    evaluators=(
        BooleanPredicateEvaluator(
            key="contains_text",
            version=1,
            expectation_type=ContainsExpectation,
            predicate=_contains,
            passed_reason="The response contains the expected text.",
            failed_reason="The response does not contain the expected text.",
        ),
    ),
    runtime_context=evaluation_runtime,
)
