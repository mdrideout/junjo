from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Annotated, Literal

import pytest
import rfc8785
from pydantic import BaseModel, Field

import junjo.agent as agent_api
import junjo.agent.testing as agent_testing_api
from junjo import Agent, AgentLimits, ModelDriverBinding, ModelDriverDescriptor, Tool
from junjo._json import JsonNestingDepthError, freeze_json, thaw_json
from junjo.agent import (
    AgentConfigurationError,
    AgentExecutionResult,
    AgentInputMessage,
    AgentStateSnapshot,
    AgentUsage,
    AssistantOutputMessage,
    FinalOutputResponse,
    ModelDriverConfigurationError,
    ModelRequest,
    ModelUsage,
    ToolCall,
    ToolCallsResponse,
    ToolConfigurationError,
    ToolDefinition,
    UsageAggregateField,
)
from junjo.agent._schema import _require_lossless_core_schema, normalize_schema
from junjo.agent.messages import normalize_model_response
from junjo.agent.testing import ScriptedModelDriver

CONTRACT_ROOT = Path(__file__).resolve().parents[3] / "contracts" / "telemetry"


def nested_arrays(depth: int) -> object:
    value: object = "leaf"
    for _ in range(depth):
        value = [value]
    return value


def nested_not_schema(depth: int) -> dict[str, object]:
    value: object = True
    for _ in range(depth):
        value = {"not": value}
    assert isinstance(value, dict)
    return value


class ObjectInput(BaseModel):
    value: str


class ObjectOutput(BaseModel):
    value: str


class RenamedObjectInput(BaseModel):
    value: str


class RenamedObjectOutput(BaseModel):
    value: str


class NestedChild(BaseModel):
    title: str


class RenamedNestedChild(BaseModel):
    title: str


class NestedInput(BaseModel):
    child: NestedChild


class RenamedNestedInput(BaseModel):
    child: RenamedNestedChild


class Cat(BaseModel):
    kind: Literal["cat"]
    title: str


class Dog(BaseModel):
    kind: Literal["dog"]
    title: str


class RenamedCat(BaseModel):
    kind: Literal["cat"]
    title: str


class RenamedDog(BaseModel):
    kind: Literal["dog"]
    title: str


class PetInput(BaseModel):
    pet: Annotated[Cat | Dog, Field(discriminator="kind")]


class RenamedPetInput(BaseModel):
    pet: Annotated[RenamedCat | RenamedDog, Field(discriminator="kind")]


class TreeNode(BaseModel):
    value: str
    children: list[TreeNode] = Field(default_factory=list)


class RenamedTreeNode(BaseModel):
    value: str
    children: list[RenamedTreeNode] = Field(default_factory=list)


class OrderedFields(BaseModel):
    alpha: str
    beta: int


class ReversedFields(BaseModel):
    beta: int
    alpha: str


class AsymmetricBoundary(BaseModel):
    value: str = Field(
        validation_alias="validationValue",
        serialization_alias="serializationValue",
    )


async def noop_service(input: ObjectInput, context) -> ObjectOutput:
    return ObjectOutput(value=input.value)


def test_public_agent_namespaces_keep_core_and_deterministic_testing_boundaries_explicit() -> None:
    assert "Agent" in agent_api.__all__
    assert "AgentAdmissionError" in agent_api.__all__
    assert "AgentInternalError" in agent_api.__all__
    assert hasattr(agent_testing_api, "ScriptedModelDriver")
    assert "ScriptedModelDriver" not in agent_api.__all__


def binding(*, settings: dict[str, object] | None = None) -> ModelDriverBinding:
    return ModelDriverBinding.shared(
        descriptor=ModelDriverDescriptor(
            driver_key="scripted",
            provider="junjo",
            model="scripted-v1",
            settings=settings,
        ),
        driver=ScriptedModelDriver([]),
    )


def test_every_canonical_fingerprint_vector_matches_rfc8785_and_sha256() -> None:
    fixture = json.loads(
        (CONTRACT_ROOT / "fixtures" / "fingerprints" / "agent-structural-v1.json").read_text(encoding="utf-8")
    )

    for vector in fixture["vectors"]:
        canonical = rfc8785.dumps(vector["material"])
        prefix = "agent_sha256:" if vector["kind"] == "agent" else "tool_sha256:"
        assert canonical.decode("utf-8") == vector["canonical"], vector["name"]
        assert prefix + hashlib.sha256(canonical).hexdigest() == vector["structural_id"]


def test_every_shared_schema_profile_vector_matches_sdk_normalization() -> None:
    fixture = json.loads(
        (CONTRACT_ROOT / "fixtures" / "fingerprints" / "schema-normalization-v1.json").read_text(encoding="utf-8")
    )

    for vector in fixture["vectors"]:
        for raw_schema in vector["inputs"]:
            assert normalize_schema(raw_schema) == vector["normalized"], vector["name"]
    for vector in fixture["invalid"]:
        with pytest.raises(ValueError):
            normalize_schema(vector["input"])


def test_portable_json_depth_bound_accepts_128_and_rejects_deeper_iteratively() -> None:
    accepted = nested_arrays(128)
    assert thaw_json(freeze_json(accepted)) == accepted

    with pytest.raises(JsonNestingDepthError):
        freeze_json(nested_arrays(129))
    with pytest.raises(JsonNestingDepthError):
        freeze_json(nested_arrays(10_000))


def test_schema_and_definition_composites_enforce_the_complete_depth_bound() -> None:
    assert normalize_schema(nested_not_schema(128)) == nested_not_schema(128)
    with pytest.raises(JsonNestingDepthError):
        normalize_schema(nested_not_schema(129))

    accepted = ToolDefinition(
        name="bounded",
        description="Bounded schema.",
        input_schema=nested_not_schema(127),
        output_schema={},
    )
    assert accepted.to_json()["inputSchema"] == nested_not_schema(127)
    with pytest.raises(JsonNestingDepthError):
        ToolDefinition(
            name="too_deep",
            description="Over-depth schema.",
            input_schema=nested_not_schema(128),
            output_schema={},
        )


def test_core_schema_projection_preflight_is_iterative_for_adversarial_depth() -> None:
    schema: object = {"type": "str"}
    for _ in range(10_000):
        schema = {"type": "list", "items_schema": schema}

    _require_lossless_core_schema(schema)


def test_agent_and_tool_structural_material_are_exact_and_order_sensitive() -> None:
    first = Tool(
        name="first",
        description="First Tool.",
        input_type=ObjectInput,
        output_type=ObjectOutput,
        shared_service=noop_service,
    )
    second = Tool(
        name="second",
        description="Second Tool.",
        input_type=ObjectInput,
        output_type=ObjectOutput,
        shared_service=noop_service,
    )
    agent = Agent(
        key="fingerprint_agent",
        name="Display name excluded from structural material",
        instructions="Be exact.",
        input_type=ObjectInput,
        model=binding(settings={"small": 1e-7, "negativeZero": -0.0}),
        tools=[first, second],
        output_type=ObjectOutput,
        limits=AgentLimits(model_requests=4, tool_calls=4),
    )
    reversed_agent = Agent(
        key="fingerprint_agent",
        name="Another display name",
        instructions="Be exact.",
        input_type=ObjectInput,
        model=binding(settings={"negativeZero": -0.0, "small": 1e-7}),
        tools=[second, first],
        output_type=ObjectOutput,
        limits=AgentLimits(model_requests=4, tool_calls=4),
    )

    material = agent.structural_material()
    assert set(material) == {
        "v",
        "agentKey",
        "instructions",
        "inputSchema",
        "model",
        "tools",
        "outputSchema",
        "limits",
    }
    assert all("v" not in tool_material for tool_material in material["tools"])
    assert agent.structural_id.startswith("agent_sha256:")
    assert first.structural_id.startswith("tool_sha256:")
    assert agent.structural_id != reversed_agent.structural_id


def test_generated_schema_titles_do_not_change_language_neutral_structural_identity() -> None:
    first = Tool(
        name="same",
        description="Same semantic Tool.",
        input_type=ObjectInput,
        output_type=ObjectOutput,
        shared_service=noop_service,
    )
    renamed = Tool(
        name="same",
        description="Same semantic Tool.",
        input_type=RenamedObjectInput,
        output_type=RenamedObjectOutput,
        shared_service=noop_service,
    )
    first_agent = Agent(
        key="same_agent",
        name="First display name",
        instructions="Be exact.",
        input_type=ObjectInput,
        model=binding(),
        tools=[first],
        output_type=ObjectOutput,
    )
    renamed_agent = Agent(
        key="same_agent",
        name="Second display name",
        instructions="Be exact.",
        input_type=RenamedObjectInput,
        model=binding(),
        tools=[renamed],
        output_type=RenamedObjectOutput,
    )

    assert first.structural_id == renamed.structural_id
    assert first_agent.structural_id == renamed_agent.structural_id
    assert '"title"' not in json.dumps(first_agent.structural_material())


def test_nested_schema_definition_names_are_canonical_but_title_properties_are_preserved() -> None:
    first = Tool(
        name="nested",
        description="Nested contract.",
        input_type=NestedInput,
        output_type=ObjectOutput,
        shared_service=noop_service,
    )
    renamed = Tool(
        name="nested",
        description="Nested contract.",
        input_type=RenamedNestedInput,
        output_type=ObjectOutput,
        shared_service=noop_service,
    )

    assert first.structural_id == renamed.structural_id
    assert first.input_schema == renamed.input_schema
    assert first.input_schema["properties"] == {"child": {"$ref": "#/$defs/d0"}}
    definitions = first.input_schema["$defs"]
    assert isinstance(definitions, Mapping)
    assert definitions["d0"]["properties"] == {"title": {"type": "string"}}


def test_discriminated_union_definition_mapping_is_canonical_across_class_renames() -> None:
    first = Tool(
        name="pet",
        description="Discriminated pet contract.",
        input_type=PetInput,
        output_type=ObjectOutput,
        shared_service=noop_service,
    )
    renamed = Tool(
        name="pet",
        description="Discriminated pet contract.",
        input_type=RenamedPetInput,
        output_type=ObjectOutput,
        shared_service=noop_service,
    )

    assert first.structural_id == renamed.structural_id
    assert first.input_schema == renamed.input_schema
    pet_schema = first.input_schema["properties"]["pet"]
    assert pet_schema["discriminator"]["mapping"] == {
        "cat": "#/$defs/d0",
        "dog": "#/$defs/d1",
    }
    fixture = json.loads(
        (CONTRACT_ROOT / "fixtures" / "fingerprints" / "agent-structural-v1.json").read_text(encoding="utf-8")
    )
    vector = next(item for item in fixture["vectors"] if item["name"] == "tool_normalized_schema_profile")
    assert first.structural_material() == vector["material"]
    assert first.structural_id == vector["structural_id"]


def test_recursive_local_definition_cycles_are_canonical_across_class_renames() -> None:
    first = Agent(
        key="tree",
        name="Tree",
        instructions="Read a recursive tree.",
        input_type=TreeNode,
        model=binding(),
        tools=[],
        output_type=ObjectOutput,
    )
    renamed = Agent(
        key="tree",
        name="Renamed Tree",
        instructions="Read a recursive tree.",
        input_type=RenamedTreeNode,
        model=binding(),
        tools=[],
        output_type=ObjectOutput,
    )

    assert first.structural_id == renamed.structural_id
    assert first.input_schema == renamed.input_schema
    assert first.input_schema["$ref"] == "#/$defs/d0"
    assert first.input_schema["$defs"]["d0"]["properties"]["children"]["items"] == {"$ref": "#/$defs/d0"}
    first_tool = Tool(
        name="tree",
        description="Recursive tree contract.",
        input_type=TreeNode,
        output_type=ObjectOutput,
        shared_service=noop_service,
    )
    renamed_tool = Tool(
        name="tree",
        description="Recursive tree contract.",
        input_type=RenamedTreeNode,
        output_type=ObjectOutput,
        shared_service=noop_service,
    )
    assert first_tool.structural_id == renamed_tool.structural_id


def test_schema_normalization_is_independent_of_object_insertion_order() -> None:
    cat = {"type": "object", "properties": {"kind": {"const": "cat"}}}
    dog = {"properties": {"kind": {"const": "dog"}}, "type": "object"}
    pet = {
        "oneOf": [{"$ref": "#/$defs/Cat"}, {"$ref": "#/$defs/Dog"}],
        "discriminator": {
            "propertyName": "kind",
            "mapping": {"dog": "#/$defs/Dog", "cat": "#/$defs/Cat"},
        },
    }
    first = {
        "$defs": {"Dog": dog, "Cat": cat},
        "type": "object",
        "properties": {"pet": pet},
    }
    reversed_order = {
        "properties": {
            "pet": {
                "discriminator": {
                    "mapping": {"cat": "#/$defs/RenamedCat", "dog": "#/$defs/RenamedDog"},
                    "propertyName": "kind",
                },
                "oneOf": [
                    {"$ref": "#/$defs/RenamedCat"},
                    {"$ref": "#/$defs/RenamedDog"},
                ],
            }
        },
        "type": "object",
        "$defs": {"RenamedCat": dict(reversed(list(cat.items()))), "RenamedDog": dog},
    }

    assert normalize_schema(first) == normalize_schema(reversed_order)


def test_set_valued_schema_arrays_do_not_leak_field_declaration_order() -> None:
    first = Tool(
        name="ordered",
        description="Order-independent object contract.",
        input_type=OrderedFields,
        output_type=ObjectOutput,
        shared_service=noop_service,
    )
    reversed_fields = Tool(
        name="ordered",
        description="Order-independent object contract.",
        input_type=ReversedFields,
        output_type=ObjectOutput,
        shared_service=noop_service,
    )

    assert first.input_schema == reversed_fields.input_schema
    assert first.input_schema["required"] == ("alpha", "beta")
    assert first.structural_id == reversed_fields.structural_id


def test_schema_profile_sorts_set_arrays_but_preserves_applicator_order() -> None:
    first = {
        "type": ["null", "string"],
        "enum": ["z", "a", 3],
        "dependentRequired": {"beta": ["z", "a"]},
        "oneOf": [{"const": "first"}, {"const": "second"}],
    }
    reordered = {
        "oneOf": [{"const": "first"}, {"const": "second"}],
        "dependentRequired": {"beta": ["a", "z"]},
        "enum": [3, "a", "z"],
        "type": ["string", "null"],
    }

    assert normalize_schema(first) == normalize_schema(reordered)
    reversed_applicator = dict(reordered)
    reversed_applicator["oneOf"] = list(reversed(reordered["oneOf"]))
    assert normalize_schema(first) != normalize_schema(reversed_applicator)


def test_schema_enum_uses_rfc8785_numeric_order_and_duplicate_identity() -> None:
    first = normalize_schema({"enum": [1e-7, -0.0, 1e21]})
    reordered = normalize_schema({"enum": [1e21, 1e-7, -0.0]})

    assert first == reordered
    with pytest.raises(ValueError):
        normalize_schema({"enum": [-0.0, 0]})


@pytest.mark.parametrize(
    "arguments",
    [
        {"value": 9_007_199_254_740_992},
        {"value": -9_007_199_254_740_992},
        {"value": "\ud800"},
        {"\ud800": "value"},
    ],
)
def test_public_tool_call_boundary_rejects_nonportable_ijson(arguments: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ToolCall(id="call", name="tool", arguments=arguments)


def test_non_payload_agent_scalars_also_reject_nonportable_ijson() -> None:
    with pytest.raises(ValueError):
        ModelUsage(total_tokens=9_007_199_254_740_992)
    with pytest.raises(ValueError):
        ToolCall(id="\ud800", name="tool", arguments={})
    with pytest.raises(ValueError):
        ToolCallsResponse(
            tool_calls=[ToolCall(id="call", name="tool", arguments={})],
            assistant_text="\ud800",
        )
    with pytest.raises(AgentConfigurationError):
        Agent(
            key="portable",
            name="\ud800",
            instructions="safe",
            input_type=ObjectInput,
            model=binding(),
            tools=[],
            output_type=ObjectOutput,
        )
    with pytest.raises(ModelDriverConfigurationError):
        ModelDriverDescriptor(
            driver_key="driver",
            provider="\ud800",
            model="model",
        )
    with pytest.raises(ToolConfigurationError):
        Tool(
            name="tool",
            description="\ud800",
            input_type=ObjectInput,
            output_type=ObjectOutput,
            shared_service=noop_service,
        )


@pytest.mark.parametrize(
    "settings",
    [
        {"unsafe": 9007199254740992},
        {"unsafe": -9007199254740992},
        {"surrogate": "\ud800"},
    ],
)
def test_agent_construction_rejects_non_interoperable_ijson(settings: dict[str, object]) -> None:
    with pytest.raises(AgentConfigurationError):
        Agent(
            key="invalid",
            name="Invalid",
            instructions="Reject invalid structural material.",
            input_type=ObjectInput,
            model=binding(settings=settings),
            tools=[],
            output_type=ObjectOutput,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_driver_descriptor_rejects_nonfinite_settings(value: float) -> None:
    with pytest.raises(ModelDriverConfigurationError):
        ModelDriverDescriptor(
            driver_key="invalid",
            provider="invalid",
            model="invalid",
            settings={"value": value},
        )


def test_tool_rejects_invalid_name_scalar_input_and_lone_surrogate() -> None:
    with pytest.raises(ToolConfigurationError):
        Tool(
            name="invalid name",
            description="Invalid.",
            input_type=ObjectInput,
            output_type=ObjectOutput,
            shared_service=noop_service,
        )
    with pytest.raises(ToolConfigurationError):
        Tool(
            name="scalar",
            description="Invalid scalar input.",
            input_type=str,
            output_type=ObjectOutput,
            shared_service=noop_service,
        )
    with pytest.raises(ToolConfigurationError):
        Tool(
            name="surrogate",
            description="\ud800",
            input_type=ObjectInput,
            output_type=ObjectOutput,
            shared_service=noop_service,
        )


def test_boundary_declarations_reject_asymmetric_schemas_and_lossy_collections() -> None:
    with pytest.raises(AgentConfigurationError, match="identical normalized"):
        Agent(
            key="asymmetric",
            name="Asymmetric",
            instructions="Reject asymmetric schemas.",
            input_type=AsymmetricBoundary,
            model=binding(),
            tools=(),
            output_type=ObjectOutput,
        )
    with pytest.raises(ToolConfigurationError, match="identical normalized"):
        Tool(
            name="asymmetric",
            description="Asymmetric boundary.",
            input_type=ObjectInput,
            output_type=AsymmetricBoundary,
            shared_service=noop_service,
        )
    with pytest.raises(AgentConfigurationError, match="identical normalized"):
        Agent(
            key="set_output",
            name="Set output",
            instructions="Reject lossy collections.",
            input_type=ObjectInput,
            model=binding(),
            tools=(),
            output_type=set[int],
        )
    with pytest.raises(AgentConfigurationError, match="identical normalized"):
        Agent(
            key="integer_keys",
            name="Integer keys",
            instructions="Reject coercive object names.",
            input_type=ObjectInput,
            model=binding(),
            tools=(),
            output_type=dict[int, str],
        )


@pytest.mark.parametrize(
    "candidate",
    [
        {"v": True, "type": "final_output", "output": {"value": "x"}},
        {
            "v": 1,
            "type": "final_output",
            "output": {"value": "x"},
            "usage": {"v": True, "inputTokens": 1},
        },
    ],
)
def test_bool_is_not_accepted_as_contract_version(candidate: object) -> None:
    with pytest.raises(ValueError):
        normalize_model_response(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        {"v": 1, "type": "final_output", "output": {"value": "x"}, "usage": None},
        {
            "v": 1,
            "type": "final_output",
            "output": {"value": "x"},
            "usage": {"v": 1, "inputTokens": None},
        },
        {
            "v": 1,
            "type": "tool_calls",
            "calls": [{"id": "c", "name": "tool", "arguments": {}}],
            "usage": None,
        },
        {
            "v": 1,
            "type": "tool_calls",
            "calls": [{"id": "c", "name": "tool", "arguments": {}}],
            "usage": {"v": 1, "totalTokens": None},
        },
    ],
)
def test_explicit_null_usage_members_are_not_treated_as_absent(
    candidate: object,
) -> None:
    with pytest.raises(ValueError):
        normalize_model_response(candidate)


def test_bool_is_not_accepted_for_ordinal_usage_or_limits() -> None:
    with pytest.raises(ValueError):
        ModelUsage(input_tokens=True)
    with pytest.raises(ValueError):
        AgentLimits(model_requests=True, tool_calls=1)
    with pytest.raises(ValueError):
        ModelRequest(
            agent_key="agent",
            run_id="run",
            ordinal=True,
            instructions="",
            messages=[],
            tools=[],
            output_schema={},
        )


@pytest.mark.parametrize(
    "usage",
    [
        lambda: AgentUsage(model_responses=True),
        lambda: AgentUsage(model_responses=-1),
        lambda: AgentUsage(fields={"unsupported": UsageAggregateField(sum=1, observations=1)}),
        lambda: AgentUsage(fields={"inputTokens": UsageAggregateField(sum=-1, observations=1)}),
        lambda: AgentUsage(fields={"inputTokens": UsageAggregateField(sum=1, observations=0)}),
    ],
)
def test_public_usage_aggregate_rejects_invalid_invariants(usage) -> None:
    with pytest.raises((TypeError, ValueError)):
        usage()


def test_usage_field_observations_cannot_exceed_response_count() -> None:
    with pytest.raises(ValueError, match="cannot exceed model_responses"):
        AgentUsage(
            model_responses=1,
            fields={"inputTokens": UsageAggregateField(sum=2, observations=2)},
        )


def _result(**overrides: object) -> AgentExecutionResult[ObjectOutput]:
    values: dict[str, object] = {
        "agent_key": "agent",
        "name": "Agent",
        "definition_id": "definition",
        "structural_id": f"agent_sha256:{'a' * 64}",
        "run_id": "run",
        "output": ObjectOutput(value="done"),
        "transcript": (
            AgentInputMessage({"value": "question"}),
            AssistantOutputMessage({"value": "done"}),
        ),
        "usage": AgentUsage(model_responses=1),
        "model_request_count": 1,
        "tool_call_requested_count": 0,
        "tool_call_admitted_count": 0,
        "tool_call_started_count": 0,
        "tool_call_completed_count": 0,
    }
    values.update(overrides)
    return AgentExecutionResult(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("agent_key", ""),
        ("name", "\ud800"),
        ("definition_id", ""),
        ("run_id", ""),
        ("structural_id", "agent_sha256:not-a-digest"),
    ],
)
def test_result_rejects_invalid_identity(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        _result(**{field: value})


@pytest.mark.parametrize(
    "overrides",
    [
        {"model_request_count": -1},
        {
            "tool_call_requested_count": 0,
            "tool_call_admitted_count": 1,
        },
        {
            "tool_call_admitted_count": 0,
            "tool_call_started_count": 1,
        },
        {
            "tool_call_started_count": 0,
            "tool_call_completed_count": 1,
        },
        {
            "usage": AgentUsage(model_responses=2),
            "model_request_count": 1,
        },
    ],
)
def test_result_rejects_impossible_counts(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _result(**overrides)


def test_result_rejects_malformed_or_incomplete_transcript() -> None:
    with pytest.raises(TypeError, match="AgentMessage"):
        _result(transcript=(object(),))
    with pytest.raises(ValueError, match="cannot be empty"):
        _result(transcript=())
    with pytest.raises(ValueError, match="end with"):
        _result(transcript=(AgentInputMessage({"value": "question"}),))


def test_model_request_rejects_malformed_and_duplicate_members() -> None:
    common = {
        "agent_key": "agent",
        "run_id": "run",
        "ordinal": 1,
        "instructions": "",
        "output_schema": {},
    }
    with pytest.raises(TypeError, match="AgentMessage"):
        ModelRequest(messages=[object()], tools=[], **common)
    with pytest.raises(TypeError, match="ToolDefinition"):
        ModelRequest(messages=[], tools=[object()], **common)

    definition = ToolDefinition(
        name="duplicate",
        description="",
        input_schema={},
        output_schema={},
    )
    with pytest.raises(ValueError, match="unique"):
        ModelRequest(messages=[], tools=[definition, definition], **common)


def _state_snapshot(**overrides: object) -> AgentStateSnapshot:
    values: dict[str, object] = {
        "input": {"question": "fixture?"},
        "history": [],
        "transcript": [{"type": "agent_input"}],
        "model_iteration": 1,
        "model_request_count": 1,
        "tool_call_requested_count": 1,
        "tool_call_admitted_count": 1,
        "tool_call_started_count": 1,
        "tool_call_completed_count": 0,
        "usage": AgentUsage(model_responses=1),
        "admitted_tool_call_ids": ["call-1"],
        "pending_tool_call_ids": ["call-1"],
        "completed_tool_call_ids": [],
        "final_output_available": False,
        "final_output": None,
        "terminal_reason": None,
    }
    values.update(overrides)
    return AgentStateSnapshot(**values)  # type: ignore[arg-type]


def test_public_agent_state_snapshot_is_detached_immutable_and_json_projectable() -> None:
    source = {"question": "fixture?"}
    snapshot = _state_snapshot(input=source)
    source["question"] = "mutated"

    assert snapshot.to_json()["input"] == {"question": "fixture?"}
    with pytest.raises(TypeError):
        snapshot.input["question"] = "mutated"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        snapshot.terminal_reason = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"model_iteration": 2},
        {"tool_call_admitted_count": 0},
        {"usage": AgentUsage(model_responses=2)},
        {"pending_tool_call_ids": []},
        {"completed_tool_call_ids": ["call-1"]},
        {"final_output_available": 1},
    ],
)
def test_public_agent_state_snapshot_rejects_incoherent_evidence(
    overrides: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        _state_snapshot(**overrides)


def test_typed_tool_response_rejects_duplicate_ids_during_runtime_normalization() -> None:
    response = ToolCallsResponse(
        tool_calls=[
            ToolCall(id="duplicate", name="first", arguments={}),
            ToolCall(id="duplicate", name="second", arguments={}),
        ]
    )

    with pytest.raises(ValueError):
        normalize_model_response(response)


def test_typed_response_constructors_reject_malformed_members() -> None:
    with pytest.raises(TypeError):
        ToolCallsResponse(tool_calls=[object()])
    with pytest.raises(TypeError):
        ToolCallsResponse(
            tool_calls=[ToolCall(id="call", name="tool", arguments={})],
            usage=object(),
        )
    with pytest.raises(TypeError):
        FinalOutputResponse(output={"value": "x"}, usage=object())
