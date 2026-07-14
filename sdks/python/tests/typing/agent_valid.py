"""Static typing proof for the public Agent generics."""

from typing import assert_type

from pydantic import BaseModel

from junjo import Agent, ModelDriverBinding, ModelDriverDescriptor, Tool
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
