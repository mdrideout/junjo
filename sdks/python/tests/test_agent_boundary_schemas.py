from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, Field, TypeAdapter
from typing_extensions import TypedDict

from junjo import Agent, ModelDriverBinding, ModelDriverDescriptor, Tool
from junjo._json import JsonBoundaryError, thaw_json
from junjo.agent import FinalOutputResponse, ToolCall, ToolCallsResponse, ToolConfigurationError
from junjo.agent.testing import ScriptedModelDriver


class TypeFieldModel(BaseModel):
    type: str


@dataclass
class TypeFieldDataclass:
    type: str


class TypeFieldTypedDict(TypedDict):
    type: str


class TypeEvent(BaseModel):
    kind: Literal["type"]
    value: str


class OtherEvent(BaseModel):
    kind: Literal["other"]
    value: str


Event = Annotated[TypeEvent | OtherEvent, Field(discriminator="kind")]


class EventBatch(BaseModel):
    events: list[Event]


class SchemaShapedData(BaseModel):
    value: dict[str, str] = Field(default={"type": "set"}, examples=[{"type": "frozenset"}])


def model_binding(script: list[object]) -> ModelDriverBinding:
    return ModelDriverBinding.shared(
        descriptor=ModelDriverDescriptor(
            driver_key="scripted",
            provider="junjo",
            model="scripted-v1",
            fixture=True,
        ),
        driver=ScriptedModelDriver(script),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("boundary_type", "payload"),
    [
        (TypeFieldModel, {"type": "record"}),
        (TypeFieldDataclass, {"type": "record"}),
        (TypeFieldTypedDict, {"type": "record"}),
        (Event, {"kind": "type", "value": "record"}),
        (EventBatch, {"events": [{"kind": "type", "value": "record"}]}),
    ],
    ids=["model-field", "dataclass-field", "typed-dict-field", "union-tag", "nested-union-tag"],
)
async def test_schema_names_round_trip_through_agent_and_tool_boundaries(boundary_type, payload) -> None:
    received = []

    async def echo(input, context):
        received.append(input)
        return input

    tool = Tool(
        name="echo",
        description="Return the supplied value.",
        input_type=boundary_type,
        output_type=boundary_type,
        shared_service=echo,
    )
    agent = Agent(
        key="schema_names",
        name="Schema names",
        instructions="Preserve the supplied value.",
        input_type=boundary_type,
        output_type=boundary_type,
        tools=[tool],
        model=model_binding(
            [
                ToolCallsResponse(tool_calls=[ToolCall(id="echo-1", name="echo", arguments=payload)]),
                FinalOutputResponse(output=payload),
            ]
        ),
    )

    result = await agent.execute(payload, dependencies=None)

    assert received == [result.output]
    assert TypeAdapter(boundary_type).dump_python(result.output, mode="json") == payload
    assert agent.input_schema == agent.output_schema == tool.input_schema == tool.output_schema


def test_schema_shaped_defaults_and_examples_remain_application_data() -> None:
    async def echo(input, context):
        return input

    tool = Tool(
        name="schema_data",
        description="Preserve schema-shaped data.",
        input_type=SchemaShapedData,
        output_type=SchemaShapedData,
        shared_service=echo,
    )
    agent = Agent(
        key="schema_data",
        name="Schema data",
        instructions="Preserve schema-shaped data.",
        input_type=SchemaShapedData,
        output_type=SchemaShapedData,
        tools=[tool],
        model=model_binding([]),
    )

    assert agent.input_schema == agent.output_schema == tool.input_schema == tool.output_schema
    value_schema = thaw_json(agent.input_schema)["properties"]["value"]
    assert value_schema["default"] == {"type": "set"}
    assert value_schema["examples"] == [{"type": "frozenset"}]


@pytest.mark.parametrize("collection_type", [set[str], frozenset[str], Iterable[str], dict[int, str]])
@pytest.mark.parametrize("boundary", ["input_type", "output_type"])
def test_lossy_types_inside_named_fields_are_still_rejected(collection_type, boundary) -> None:
    class LossyField(BaseModel):
        type: collection_type

    async def echo(input, context):
        return input

    declarations = {"input_type": TypeFieldModel, "output_type": TypeFieldModel, boundary: LossyField}
    with pytest.raises(ToolConfigurationError, match=f"Tool {boundary}:") as caught:
        Tool(
            name="lossy",
            description="Reject a nested lossy boundary.",
            shared_service=echo,
            **declarations,
        )

    assert isinstance(caught.value.__cause__, JsonBoundaryError)
    assert str(caught.value.__cause__) in str(caught.value)
