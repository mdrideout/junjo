"""Deterministic application definitions shared by normal and evaluation runs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, cast

from agents import (
    Agent as OpenAIAgent,
)
from agents import (
    AgentOutputSchemaBase,
    GuardrailFunctionOutput,
    Handoff,
    ModelResponse,
    ModelSettings,
    ModelTracing,
    OutputGuardrail,
    RunConfig,
    Tool,
    TResponseInputItem,
)
from agents.testing import ScriptedModel, assistant_message, function_call
from agents.tracing import generation_span
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
from junjo.plugins.openai_agents import (
    AgentToolInvocation,
    WorkflowToolInvocation,
    agent_as_tool,
    workflow_as_tool,
)
from openai.types.responses.response_prompt_param import ResponsePromptParam
from pydantic import BaseModel, ConfigDict

OPENAI_AGENT_NAME = "Local place coordinator"
OPENAI_REVIEWER_NAME = "Local place reviewer"
OPENAI_WORKFLOW_NAME = "Authentic local place recommendation"
OPENAI_REVIEW_WORKFLOW_NAME = "Local place realism review"
WORKFLOW_NAME = "Local place workflow"
JUNJO_AGENT_NAME = "Local place specialist"


class CompleteTracingScriptedModel(ScriptedModel):
    """Deterministic model that demonstrates a normally populated model span.

    The upstream test-only ``ScriptedModel`` emits an intentionally empty
    Generation span. This example adapter disables that placeholder and uses
    the public model-tracing arguments to populate the same source fields a
    real model adapter provides. Junjo's bridge only translates source data;
    it does not reach into a model implementation to reconstruct missing data.
    """

    def __init__(self, script: Iterable[Any], *, model_name: str) -> None:
        super().__init__(script, emit_traces=False)
        self.model_name = model_name

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        include_data = tracing.include_data()
        trace_input: Sequence[Mapping[str, Any]] | None = None
        if include_data:
            trace_input_items = (
                cast(list[Mapping[str, Any]], list(input))
                if isinstance(input, list)
                else [{"role": "user", "content": input}]
            )
            if system_instructions:
                trace_input_items.insert(0, {"role": "system", "content": system_instructions})
            trace_input = trace_input_items

        trace_model_config = {
            **model_settings.to_traceable_dict(),
            "junjo.model.fixture": True,
        }
        with generation_span(
            input=trace_input,
            model=self.model_name,
            model_config=trace_model_config,
            disabled=tracing.is_disabled(),
        ) as span:
            response = await super().get_response(
                system_instructions,
                input,
                model_settings,
                tools,
                output_schema,
                handoffs,
                tracing,
                previous_response_id=previous_response_id,
                conversation_id=conversation_id,
                prompt=prompt,
            )
            if include_data:
                span.span_data.output = [item.model_dump(mode="json") for item in response.output]
                span.span_data.usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            return response


class LocalPlaceInput(BaseModel):
    """One request used across external and native evaluation scopes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message: str


class LocalPlaceOutput(BaseModel):
    """Detached result returned by native Junjo execution boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    response: str


class LocalPlaceState(BaseState):
    message: str
    response: str | None = None


class LocalPlaceStore(BaseStore[LocalPlaceState]):
    async def set_response(self, response: str) -> None:
        await self.set_state({"response": response})


class ChooseLocalPlaceNode(Node[LocalPlaceStore]):
    async def service(self, store: LocalPlaceStore) -> None:
        state = await store.get_state()
        await store.set_response(f"For {state.message}, try the Brooklyn Botanic Garden near Prospect Park.")


def build_workflow(input_value: LocalPlaceInput) -> Workflow[LocalPlaceState, LocalPlaceStore]:
    """Build a fresh native Workflow for one invocation."""

    def graph_factory() -> Graph:
        node = ChooseLocalPlaceNode()
        return Graph(source=node, sinks=[node], edges=[])

    return Workflow(
        name=WORKFLOW_NAME,
        graph_factory=graph_factory,
        store_factory=lambda: LocalPlaceStore(initial_state=LocalPlaceState(message=input_value.message)),
    )


def build_junjo_agent(input_value: LocalPlaceInput) -> Agent:
    """Build a fresh native Junjo Agent for one invocation."""

    driver = ScriptedModelDriver(
        [
            FinalOutputResponse(
                output={"response": (f"For {input_value.message}, visit the Brooklyn Museum and nearby Prospect Park.")}
            )
        ]
    )
    return Agent(
        key="local_place_specialist",
        name=JUNJO_AGENT_NAME,
        instructions="Recommend one geographically plausible local place.",
        input_type=LocalPlaceInput,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="example",
                model="deterministic-local-place-v1",
                fixture=True,
            ),
            driver=driver,
        ),
        output_type=LocalPlaceOutput,
        tools=(),
        limits=AgentLimits(model_requests=1, tool_calls=1),
    )


def build_openai_agent() -> OpenAIAgent[None]:
    """Build the outer OpenAI Agent with native Junjo tools."""

    workflow_tool = workflow_as_tool(
        name="run_local_place_workflow",
        description="Run the deterministic local-place Workflow.",
        input_type=LocalPlaceInput,
        workflow_factory=lambda input_value: WorkflowToolInvocation(workflow=build_workflow(input_value)),
        output_projector=lambda result, _input: result.state.response,
    )
    agent_tool = agent_as_tool(
        name="run_local_place_agent",
        description="Ask the native Junjo Agent for a local-place recommendation.",
        input_type=LocalPlaceInput,
        agent_factory=lambda input_value: AgentToolInvocation(
            agent=build_junjo_agent(input_value),
            input=input_value,
            dependencies=None,
        ),
        output_projector=lambda result, _input: result.output.response,
    )
    reviewer = OpenAIAgent(
        name=OPENAI_REVIEWER_NAME,
        instructions="Review whether the proposed places are geographically plausible.",
        model=CompleteTracingScriptedModel(
            [[assistant_message("The Brooklyn places are geographically plausible.")]],
            model_name="deterministic-reviewer-v1",
        ),
    )
    reviewer_tool = reviewer.as_tool(
        tool_name="review_local_place_options",
        tool_description="Review local-place recommendations for geographic plausibility.",
        run_config=RunConfig(workflow_name=OPENAI_REVIEW_WORKFLOW_NAME),
    )
    model = CompleteTracingScriptedModel(
        [
            [
                function_call(
                    "run_local_place_workflow",
                    {"message": "a calm afternoon"},
                    call_id="workflow-call",
                )
            ],
            [
                function_call(
                    "review_local_place_options",
                    {"input": "Review the Brooklyn Botanic Garden and Brooklyn Museum suggestions."},
                    call_id="reviewer-call",
                )
            ],
            [
                function_call(
                    "run_local_place_agent",
                    {"message": "a rainy afternoon"},
                    call_id="agent-call",
                )
            ],
            [assistant_message("Try the Brooklyn Botanic Garden, Brooklyn Museum, and nearby Prospect Park.")],
        ],
        model_name="deterministic-coordinator-v1",
    )
    return OpenAIAgent(
        name=OPENAI_AGENT_NAME,
        instructions="Use the available Junjo tools, then provide one concise answer.",
        model=model,
        tools=[workflow_tool, reviewer_tool, agent_tool],
        output_guardrails=[
            OutputGuardrail(
                guardrail_function=_local_place_output_guardrail,
                name="local place realism",
            )
        ],
    )


def _local_place_output_guardrail(
    _context: object,
    _agent: object,
    output: object,
) -> GuardrailFunctionOutput:
    """Record one deterministic, passing application guardrail."""

    text = str(output)
    is_local = "Brooklyn" in text or "Prospect Park" in text
    return GuardrailFunctionOutput(
        output_info={"contains_local_place": is_local},
        tripwire_triggered=not is_local,
    )
