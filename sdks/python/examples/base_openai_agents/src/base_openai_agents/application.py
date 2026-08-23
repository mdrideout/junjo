"""Deterministic application definitions shared by normal and evaluation runs."""

from __future__ import annotations

from agents import Agent as OpenAIAgent
from agents.testing import ScriptedModel, assistant_message, function_call
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
from pydantic import BaseModel, ConfigDict

OPENAI_AGENT_NAME = "Local place coordinator"
WORKFLOW_NAME = "Local place workflow"
JUNJO_AGENT_NAME = "Local place specialist"


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
    model = ScriptedModel(
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
                    "run_local_place_agent",
                    {"message": "a rainy afternoon"},
                    call_id="agent-call",
                )
            ],
            [assistant_message("Try the Brooklyn Botanic Garden, Brooklyn Museum, and nearby Prospect Park.")],
        ]
    )
    return OpenAIAgent(
        name=OPENAI_AGENT_NAME,
        instructions="Use the available Junjo tools, then provide one concise answer.",
        model=model,
        tools=[workflow_tool, agent_tool],
    )
