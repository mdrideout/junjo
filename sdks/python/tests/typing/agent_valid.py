"""Static typing proof for the public Agent generics."""

from typing import assert_type

from pydantic import BaseModel

from junjo import Agent, BaseState, BaseStore, ModelDriverBinding, ModelDriverDescriptor, Tool
from junjo.agent import AgentExecutionResult, AgentRunContext
from junjo.agent.testing import ScriptedModelDriver


class Dependencies:
    pass


class Input(BaseModel):
    question: str


class Output(BaseModel):
    answer: str


class ToolInput(BaseModel):
    query: str


class ToolOutput(BaseModel):
    value: str


async def lookup(
    input: ToolInput,
    context: AgentRunContext[Dependencies],
) -> ToolOutput:
    return ToolOutput(value=f"{context.dependencies!r}:{input.query}")


tool: Tool[ToolInput, ToolOutput, Dependencies] = Tool(
    name="lookup",
    description="Look up one value.",
    input_type=ToolInput,
    output_type=ToolOutput,
    shared_service=lookup,
)
agent: Agent[Input, Output, Dependencies] = Agent(
    key="typed",
    name="Typed Agent",
    instructions="Return typed evidence.",
    input_type=Input,
    model=ModelDriverBinding.shared(
        descriptor=ModelDriverDescriptor(
            driver_key="scripted",
            provider="junjo",
            model="scripted-v1",
        ),
        driver=ScriptedModelDriver([]),
    ),
    tools=[tool],
    output_type=Output,
)


async def proof() -> None:
    result = await agent.execute(
        Input(question="typed?"),
        dependencies=Dependencies(),
    )
    assert_type(result, AgentExecutionResult[Output])
    assert_type(result.output, Output)


# An application's Store actions and detached result keep their concrete types.
class AppState(BaseState):
    findings: list[str]


class AppStore(BaseStore[AppState]):
    async def add_finding(self, value: str) -> None:
        state = await self.get_state()
        await self.set_state({"findings": [*state.findings, value]})


async def stored_lookup(input: ToolInput, context: AgentRunContext[Dependencies, AppStore]) -> ToolOutput:
    await context.store.add_finding(input.query)
    assert_type(await context.store.get_state(), AppState)
    return ToolOutput(value=input.query)


stored_tool = Tool[ToolInput, ToolOutput, Dependencies, AppStore](
    name="stored_lookup",
    description="Record the lookup.",
    input_type=ToolInput,
    output_type=ToolOutput,
    shared_service=stored_lookup,
)
stored_agent = Agent[Input, Output, Dependencies, AppState, AppStore](
    key="stored",
    name="Stored Agent",
    instructions="Use stored evidence.",
    input_type=Input,
    output_type=Output,
    model=agent.model,
    tools=[stored_tool],
    store_factory=lambda: AppStore(AppState(findings=[])),
)


async def stored_proof() -> None:
    store = AppStore(AppState(findings=[]))
    result = await stored_agent.execute(Input(question="typed?"), dependencies=Dependencies(), store=store)
    assert_type(result, AgentExecutionResult[Output, AppState])
    assert_type(result.application_state, AppState | None)
