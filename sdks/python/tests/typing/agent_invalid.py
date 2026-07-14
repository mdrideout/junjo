"""Intentional public Agent typing errors used by the static contract test."""

from pydantic import BaseModel

from junjo import Agent, ModelDriverBinding, ModelDriverDescriptor, Tool
from junjo.agent import AgentRunContext
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


async def bad_service(
    input: ToolInput,
    context: AgentRunContext[Dependencies],
) -> Input:
    return Input(question=input.query)


bad_tool: Tool[ToolInput, ToolOutput, Dependencies] = Tool(
    name="bad",
    description="Wrong output type.",
    input_type=ToolInput,
    output_type=ToolOutput,
    shared_service=bad_service,
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
    tools=[bad_tool],
    output_type=Output,
)


async def invalid_calls() -> None:
    await agent.execute(Output(answer="wrong input"), dependencies=Dependencies())
    await agent.execute(Input(question="wrong deps"), dependencies=object())
