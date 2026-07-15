"""Actual SDK exporter equivalence for every canonical Agent producer fixture.

The canonical files are test inputs only.  This module never imports the
fixture generator: every scenario runs the public Agent/Workflow API (with
bounded fault injection only for the three explicitly internal-error cases),
captures real OpenTelemetry spans, and compares reconstructable semantics.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Any

import jsonpatch
import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from pydantic import BaseModel, ConfigDict

from junjo import (
    Agent,
    AgentLimits,
    BaseState,
    BaseStore,
    ExecutionCorrelation,
    Graph,
    Hooks,
    ModelDriverBinding,
    ModelDriverDescriptor,
    Node,
    Tool,
    Workflow,
)
from junjo.agent import (
    AgentAdmissionError,
    AgentHistoryValidationError,
    AgentInputMessage,
    AgentInputValidationError,
    AgentInternalError,
    FinalOutputResponse,
    ModelUsage,
    ToolCall,
    ToolCallsResponse,
)
from junjo.agent import _runtime as agent_runtime
from junjo.agent._state import AgentStore
from junjo.agent.testing import ScriptedError, ScriptedModelDriver

CONTRACT_ROOT = Path(__file__).resolve().parents[3] / "contracts" / "telemetry"
PRODUCER_ROOT = CONTRACT_ROOT / "fixtures" / "agent" / "producer"
EXPECTED_SCENARIOS = {
    "admission_internal_error",
    "agent_cancellation_inside_workflow_node",
    "agent_failure_inside_workflow_node",
    "agent_inside_workflow_node",
    "boundary_input_history_rejection",
    "cancelled_model_request",
    "cancelled_tool_service",
    "cancelled_workflow_tool",
    "concurrent_run_isolation",
    "direct_typed_completion",
    "final_output_validation_failure",
    "hook_failure_then_success",
    "malformed_model_response",
    "malformed_tool_arguments",
    "model_driver_failure",
    "model_request_limit_exhaustion",
    "multi_tool_first_cancellation",
    "multi_tool_first_failure",
    "nested_agent_owner_isolation",
    "nested_workflow_failure",
    "nonserializable_model_response_candidate",
    "nonserializable_tool_result_candidate",
    "ordered_multiple_tools",
    "over_budget_tool_batch",
    "standalone_agent_under_non_junjo_span",
    "terminal_commit_internal_error_partial",
    "terminal_observer_cancellation",
    "tool_invokes_nested_workflow",
    "tool_output_validation_failure",
    "tool_service_failure",
    "unexpected_internal_error",
    "unknown_tool",
    "usage_absent_vs_zero",
}


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str


class LookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str


class LookupOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class WorkflowState(BaseState):
    question: str
    answer: str | None = None


class WorkflowStore(BaseStore[WorkflowState]):
    async def answer(self, value: str) -> None:
        await self.set_state({"answer": value})


class NestedState(BaseState):
    value: str


class NestedStore(BaseStore[NestedState]):
    pass


class AgentNode(Node[WorkflowStore]):
    @property
    def name(self) -> str:
        return "agent node"

    def __init__(self, agent: Agent[Question, Answer, None]) -> None:
        super().__init__()
        self.agent = agent

    async def service(self, store: WorkflowStore) -> None:
        state = await store.get_state()
        await self.agent.execute(
            Question(question=state.question), dependencies=None
        )


class NestedNode(Node[NestedStore]):
    @property
    def name(self) -> str:
        return "nested node"

    def __init__(
        self,
        *,
        failure: bool = False,
        entered: asyncio.Event | None = None,
        inner_agent: Agent[Question, Answer, None] | None = None,
    ) -> None:
        super().__init__()
        self.failure = failure
        self.entered = entered
        self.inner_agent = inner_agent

    async def service(self, store: NestedStore) -> None:
        if self.failure:
            raise RuntimeError("nested failure")
        if self.entered is not None:
            self.entered.set()
            await asyncio.Event().wait()
        if self.inner_agent is not None:
            await self.inner_agent.execute(
                Question(question="fixture?"), dependencies=None
            )


@pytest.fixture
def span_exporter(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> InMemorySpanExporter:
    scenario = request.node.callspec.params["scenario"]
    service_name = f"svc-agent-{scenario.replace('_', '-')}"
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service_name,
                "service.namespace": "junjo.contract",
                "service.version": "2.0.0",
            }
        )
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)
    return exporter


def _usage() -> ModelUsage:
    return ModelUsage(input_tokens=10, output_tokens=4, total_tokens=14)


def _final(*, valid: bool = True, usage: ModelUsage | None = None) -> FinalOutputResponse:
    output = {"answer": "done"} if valid else {"wrong": True}
    return FinalOutputResponse(output=output, usage=_usage() if usage is None else usage)


def _calls(*names: str, usage: ModelUsage | None = None) -> ToolCallsResponse:
    return ToolCallsResponse(
        tool_calls=[
            ToolCall(
                id=f"call-{index}",
                name=name,
                arguments={"query": f"q{index}"},
            )
            for index, name in enumerate(names, start=1)
        ],
        assistant_text="Using tools",
        usage=_usage() if usage is None else usage,
    )


def _tool(
    name: str,
    service: Any,
) -> Tool[LookupInput, LookupOutput, None]:
    return Tool(
        name=name,
        description=f"Run {name}",
        input_type=LookupInput,
        output_type=LookupOutput,
        shared_service=service,
    )


def _agent(
    script: list[object] | None = None,
    *,
    driver: object | None = None,
    tools: tuple[Tool[LookupInput, LookupOutput, None], ...] | None = None,
    limits: AgentLimits | None = None,
    hooks: Hooks | None = None,
) -> Agent[Question, Answer, None]:
    selected_driver = driver or ScriptedModelDriver(script or [])
    declared_tools = tools or (_tool("lookup", _successful_service),)
    return Agent(
        key="fixture_agent",
        name="Fixture Agent",
        instructions="Answer with deterministic fixture evidence.",
        input_type=Question,
        model=ModelDriverBinding.shared(
            descriptor=ModelDriverDescriptor(
                driver_key="scripted",
                provider="junjo",
                model="scripted-v1",
            ),
            driver=selected_driver,  # type: ignore[arg-type]
        ),
        tools=declared_tools,
        output_type=Answer,
        limits=limits or AgentLimits(model_requests=4, tool_calls=4),
        hooks=hooks,
    )


async def _successful_service(
    input: LookupInput, context: object
) -> LookupOutput:
    del context
    return LookupOutput(value=f"result-{input.query.removeprefix('q')}")


async def _run_cancelled(
    coro: Any,
    entered: asyncio.Event,
    *,
    reason: str = "fixture cancellation",
) -> None:
    task = asyncio.create_task(coro)
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel(reason)
    with pytest.raises(asyncio.CancelledError):
        await task


def _nested_workflow(
    *,
    failure: bool = False,
    entered: asyncio.Event | None = None,
    inner_agent: Agent[Question, Answer, None] | None = None,
) -> Workflow:
    def graph_factory() -> Graph:
        node = NestedNode(
            failure=failure,
            entered=entered,
            inner_agent=inner_agent,
        )
        return Graph(source=node, sinks=[node], edges=[])

    return Workflow(
        name="nested workflow",
        graph_factory=graph_factory,
        store_factory=lambda: NestedStore(NestedState(value="result-1")),
        max_iterations=1,
    )


async def _run_workflow_parent(agent: Agent[Question, Answer, None]) -> None:
    def graph_factory() -> Graph:
        node = AgentNode(agent)
        return Graph(source=node, sinks=[node], edges=[])

    workflow = Workflow(
        name="outer workflow",
        graph_factory=graph_factory,
        store_factory=lambda: WorkflowStore(WorkflowState(question="fixture?")),
        max_iterations=1,
    )
    await workflow.execute()


async def _execute_scenario(  # noqa: C901
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = Question(question="fixture?")

    if scenario == "boundary_input_history_rejection":
        agent = _agent([_final()])
        with pytest.raises(AgentInputValidationError):
            await agent.execute({"invalid": True}, dependencies=None)  # type: ignore[arg-type]
        with pytest.raises(AgentHistoryValidationError):
            await agent.execute(
                question,
                dependencies=None,
                history=[AgentInputMessage({"invalid": True})],
            )
        return

    if scenario == "admission_internal_error":
        def fail_initial_evidence(self: AgentStore) -> None:
            raise RuntimeError("admission setup failed")

        monkeypatch.setattr(
            AgentStore, "_get_initial_store_owner_evidence", fail_initial_evidence
        )
        with pytest.raises(AgentAdmissionError):
            await _agent([_final()]).execute(question, dependencies=None)
        return

    if scenario == "unexpected_internal_error":
        async def fail_completion(self: object, response: object) -> None:
            raise RuntimeError("unexpected admitted runtime failure")

        monkeypatch.setattr(agent_runtime._AgentRun, "_complete", fail_completion)
        with pytest.raises(AgentInternalError):
            await _agent([_final()]).execute(question, dependencies=None)
        return

    if scenario == "terminal_commit_internal_error_partial":
        async def fail_commit(self: AgentStore, output: object) -> None:
            raise RuntimeError("terminal Store commit failed")

        monkeypatch.setattr(AgentStore, "commit_success", fail_commit)
        with pytest.raises(AgentInternalError):
            await _agent([_final()]).execute(question, dependencies=None)
        return

    if scenario in {"cancelled_model_request", "agent_cancellation_inside_workflow_node"}:
        entered = asyncio.Event()

        class BlockingDriver:
            async def request(self, request: object) -> object:
                entered.set()
                await asyncio.Event().wait()

        agent = _agent(driver=BlockingDriver())
        if scenario == "cancelled_model_request":
            await _run_cancelled(agent.execute(question, dependencies=None), entered)
        else:
            await _run_cancelled(_run_workflow_parent(agent), entered)
        return

    if scenario in {"cancelled_tool_service", "multi_tool_first_cancellation"}:
        entered = asyncio.Event()

        async def blocking_service(input: LookupInput, context: object) -> LookupOutput:
            del input, context
            entered.set()
            await asyncio.Event().wait()

        names = ("lookup", "search") if scenario.startswith("multi") else ("lookup",)
        tools = tuple(_tool(name, blocking_service) for name in names)
        agent = _agent([_calls(*names)], tools=tools)
        await _run_cancelled(agent.execute(question, dependencies=None), entered)
        return

    if scenario == "cancelled_workflow_tool":
        entered = asyncio.Event()

        async def workflow_service(input: LookupInput, context: object) -> LookupOutput:
            del input, context
            await _nested_workflow(entered=entered).execute()
            return LookupOutput(value="result-1")

        agent = _agent([_calls("lookup")], tools=(_tool("lookup", workflow_service),))
        await _run_cancelled(agent.execute(question, dependencies=None), entered)
        return

    if scenario == "terminal_observer_cancellation":
        entered = asyncio.Event()
        hooks = Hooks()

        async def slow_hook(event: object) -> None:
            del event
            entered.set()
            await asyncio.Event().wait()

        hooks.on_agent_completed(slow_hook)
        await _run_cancelled(
            _agent([_final()], hooks=hooks).execute(question, dependencies=None),
            entered,
            reason="caller cancelled delivery",
        )
        return

    if scenario == "hook_failure_then_success":
        hooks = Hooks()

        def bad_hook(event: object) -> None:
            del event
            raise RuntimeError("observer failed")

        hooks.on_agent_started(bad_hook)
        await _agent([_final()], hooks=hooks).execute(question, dependencies=None)
        return

    if scenario in {"agent_inside_workflow_node", "agent_failure_inside_workflow_node"}:
        script: list[object] = (
            [ScriptedError(RuntimeError("model_error"))]
            if "failure" in scenario
            else [_final()]
        )
        with suppress(Exception):
            await _run_workflow_parent(_agent(script))
        return

    if scenario in {
        "tool_invokes_nested_workflow",
        "nested_workflow_failure",
        "nested_agent_owner_isolation",
    }:
        failure = scenario == "nested_workflow_failure"
        inner = _agent([_final()]) if scenario == "nested_agent_owner_isolation" else None

        async def workflow_service(input: LookupInput, context: object) -> LookupOutput:
            del input, context
            result = await _nested_workflow(
                failure=failure,
                inner_agent=inner,
            ).execute()
            return LookupOutput(value=result.state.value)

        agent = _agent(
            [_calls("lookup"), _final()],
            tools=(_tool("lookup", workflow_service),),
        )
        with suppress(Exception):
            await agent.execute(
                question,
                dependencies=None,
                correlation=(
                    ExecutionCorrelation(
                        type="ai_chat.turn",
                        id="turn-fixture-001",
                    )
                    if scenario == "tool_invokes_nested_workflow"
                    else None
                ),
            )
        return

    if scenario == "standalone_agent_under_non_junjo_span":
        tracer = trace.get_tracer("external-http-server")
        with tracer.start_as_current_span("POST /chat", kind=SpanKind.SERVER):
            await _agent([_final()]).execute(question, dependencies=None)
        return

    if scenario == "concurrent_run_isolation":
        drivers = iter((ScriptedModelDriver([_final()]), ScriptedModelDriver([_final()])))
        agent = Agent(
            key="fixture_agent",
            name="Fixture Agent",
            instructions="Answer with deterministic fixture evidence.",
            input_type=Question,
            model=ModelDriverBinding.per_run(
                descriptor=ModelDriverDescriptor(
                    driver_key="scripted", provider="junjo", model="scripted-v1"
                ),
                factory=lambda: next(drivers),
            ),
            tools=(_tool("lookup", _successful_service),),
            output_type=Answer,
            limits=AgentLimits(model_requests=4, tool_calls=4),
        )
        await asyncio.gather(
            agent.execute(question, dependencies=None),
            agent.execute(question, dependencies=None),
        )
        return

    declared_names: tuple[str, ...] = ("lookup",)
    script = [_final()]
    limits = AgentLimits(model_requests=4, tool_calls=4)
    service: Any = _successful_service

    if scenario in {"ordered_multiple_tools", "over_budget_tool_batch"}:
        declared_names = ("lookup", "search")
        script = [_calls(*declared_names), _final()]
        if scenario == "over_budget_tool_batch":
            script = script[:1]
            limits = AgentLimits(model_requests=4, tool_calls=1)
    elif scenario == "multi_tool_first_failure":
        declared_names = ("lookup", "search")
        script = [_calls(*declared_names)]

        async def fail_first(input: LookupInput, context: object) -> LookupOutput:
            del input, context
            raise RuntimeError("first Tool failed")

        service = fail_first
    elif scenario == "unknown_tool":
        script = [_calls("missing")]
    elif scenario == "malformed_tool_arguments":
        script = [
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(id="call-1", name="lookup", arguments={"wrong": True})
                ],
                assistant_text="Using tools",
                usage=_usage(),
            )
        ]
    elif scenario == "malformed_model_response":
        script = [{"invalid": "response"}]
    elif scenario == "nonserializable_model_response_candidate":
        script = [object()]
    elif scenario == "model_driver_failure":
        script = [ScriptedError(RuntimeError("model_error"))]
    elif scenario == "tool_service_failure":
        script = [_calls("lookup")]

        async def fail_service(input: LookupInput, context: object) -> LookupOutput:
            del input, context
            raise RuntimeError("tool_error")

        service = fail_service
    elif scenario in {
        "tool_output_validation_failure",
        "nonserializable_tool_result_candidate",
    }:
        script = [_calls("lookup")]

        async def invalid_output(input: LookupInput, context: object) -> object:
            del input, context
            return {"wrong": True} if scenario.startswith("tool_output") else object()

        service = invalid_output
    elif scenario == "final_output_validation_failure":
        script = [_final(valid=False)]
    elif scenario == "model_request_limit_exhaustion":
        script = [_calls("lookup")]
        limits = AgentLimits(model_requests=1, tool_calls=4)
    elif scenario == "usage_absent_vs_zero":
        script = [
            _calls("lookup", usage=ModelUsage(input_tokens=0)),
            FinalOutputResponse(output={"answer": "done"}),
        ]

    tools = tuple(_tool(name, service) for name in declared_names)
    agent = _agent(script, tools=tools, limits=limits)
    with suppress(Exception):
        await agent.execute(question, dependencies=None)


def _canonical(scenario: str) -> dict[str, Any]:
    return json.loads((PRODUCER_ROOT / f"{scenario}.json").read_text(encoding="utf-8"))


def _kind(attributes: Any, name: str) -> str:
    return str(
        attributes.get("junjo.span_type")
        or attributes.get("junjo.agent.operation_type")
        or ("external" if name == "POST /chat" else "other")
    )


def _normalize_json(value: object) -> object:
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, object] = {}
    for key, item in value.items():
        if key in {
            "runId",
            "nodeRuntimeId",
            "executableDefinitionId",
            "executableRuntimeId",
            "parentExecutableDefinitionId",
            "parentExecutableRuntimeId",
            "storeId",
        }:
            result[key] = f"<{key}>"
        elif key in {
            "graphStructuralId",
            "nodeStructuralId",
            "enclosingGraphStructuralId",
            "parentExecutableStructuralId",
        }:
            result[key] = f"<{key}>"
        else:
            result[key] = _normalize_json(item)
    return result


def _identity_placeholder(key: str) -> str:
    if "structural" in key:
        return "<structural-id>"
    if "definition" in key:
        return "<definition-id>"
    if "runtime" in key:
        return "<runtime-id>"
    return "<store-id>"


def _semantic_attributes(attributes: Any, kind: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, raw in attributes.items():
        if not (key.startswith("junjo.") or key == "error.type"):
            continue
        value: object = raw
        if (key.endswith(".id") or key.endswith("_id")) and "structural_id" not in key:
            if key not in {
                "junjo.agent.tool_call.id",
                "junjo.agent.tool.structural_id",
            }:
                value = _identity_placeholder(key)
        if "structural_id" in key and key not in {
            "junjo.agent.tool.structural_id",
        }:
            if not (kind == "agent" and key == "junjo.executable_structural_id"):
                value = "<structural-id>"
        if key == "junjo.hook.callback":
            value = "<hook-callback>"
        if isinstance(value, str) and value[:1] in {"{", "["}:
            value = _normalize_json(json.loads(value))
        elif hasattr(value, "value") and isinstance(value.value, str):
            value = value.value
        result[key] = value
    return result


def _semantic_event(name: str, attributes: Any, dropped: int) -> dict[str, object]:
    projected = _semantic_attributes(attributes, "event")
    if name == "set_state" and "junjo.state_json_patch" in projected:
        projected["junjo.state_json_patch"] = "<validated-and-replayed-rfc6902>"
    if name == "exception" and "exception.stacktrace" in attributes:
        projected["exception.stacktrace"] = "<present>"
    for key in ("exception.type", "exception.message"):
        if key in attributes:
            projected[key] = attributes[key]
    return {
        "name": name,
        "attributes": projected,
        "dropped_attributes_count": dropped,
    }


def _event_sort_key(event: dict[str, object]) -> str:
    return json.dumps(event, sort_keys=True, default=dict)


def _actual_records(spans: tuple[ReadableSpan, ...]) -> list[dict[str, object]]:
    by_id = {span.context.span_id: span for span in spans if span.context is not None}
    result = []
    for span in spans:
        attributes = span.attributes or {}
        kind = _kind(attributes, span.name)
        if kind == "other":
            continue
        parent = by_id.get(span.parent.span_id) if span.parent is not None else None
        parent_kind = (
            _kind(parent.attributes or {}, parent.name) if parent is not None else None
        )
        result.append(
            {
                "kind": kind,
                "name": span.name,
                "parent_kind": parent_kind,
                "status": span.status.status_code.name,
                "attributes": _semantic_attributes(attributes, kind),
                "events": sorted(
                    (
                        _semantic_event(
                            event.name,
                            event.attributes,
                            event.dropped_attributes,
                        )
                        for event in span.events
                    ),
                    key=_event_sort_key,
                ),
                "kind_code": span.kind.name,
                "trace_flags": int(span.context.trace_flags),
                "resource": {
                    key: span.resource.attributes[key]
                    for key in (
                        "service.name",
                        "service.namespace",
                        "service.version",
                    )
                },
                "resource_dropped_attributes_count": 0,
                "dropped_attributes_count": span.dropped_attributes,
                "dropped_events_count": span.dropped_events,
                "dropped_links_count": span.dropped_links,
            }
        )
    return sorted(result, key=lambda item: json.dumps(item, sort_keys=True, default=dict))


def _canonical_records(fixture: dict[str, Any]) -> list[dict[str, object]]:
    spans = fixture["spans"]
    by_id = {span["span_id"]: span for span in spans}
    result = []
    for span in spans:
        attributes = span["attributes_json"]
        kind = _kind(attributes, span["name"])
        parent = by_id.get(span["parent_span_id"])
        parent_kind = (
            _kind(parent["attributes_json"], parent["name"]) if parent else None
        )
        status = "ERROR" if span["status_code"] == "2" else "UNSET"
        result.append(
            {
                "kind": kind,
                "name": span["name"],
                "parent_kind": parent_kind,
                "status": status,
                "attributes": _semantic_attributes(attributes, kind),
                "events": sorted(
                    (
                        _semantic_event(
                            event["name"],
                            event["attributes"],
                            event["droppedAttributesCount"],
                        )
                        for event in span["events_json"]
                    ),
                    key=_event_sort_key,
                ),
                "kind_code": span["kind"],
                "trace_flags": span["trace_flags"],
                "resource": span["resource_attributes_json"],
                "resource_dropped_attributes_count": span[
                    "resource_dropped_attributes_count"
                ],
                "dropped_attributes_count": span["dropped_attributes_count"],
                "dropped_events_count": span["dropped_events_count"],
                "dropped_links_count": span["dropped_links_count"],
            }
        )
    return sorted(result, key=lambda item: json.dumps(item, sort_keys=True, default=dict))


def _store_evidence_from_actual(
    spans: tuple[ReadableSpan, ...],
) -> list[tuple[str, list[str], int, int]]:
    owners = [
        span
        for span in spans
        if (span.attributes or {}).get("junjo.span_type")
        in {"agent", "workflow", "subflow"}
        and (
            (span.attributes or {}).get("junjo.span_type") != "agent"
            or (span.attributes or {}).get("junjo.agent.state.available") is True
        )
    ]
    evidence = []
    for owner in owners:
        attributes = owner.attributes or {}
        owner_kind = str(attributes["junjo.span_type"])
        namespace = "agent" if owner_kind == "agent" else "workflow"
        store_id = attributes[f"junjo.{namespace}.store.id"]
        events = sorted(
            (
                event
                for span in spans
                for event in span.events
                if event.name == "set_state"
                and event.attributes.get("junjo.store.id") == store_id
            ),
            key=lambda event: event.attributes["junjo.store.transition.sequence"],
        )
        projection = json.loads(attributes[f"junjo.{namespace}.state.start"])
        for event in events:
            projection = jsonpatch.JsonPatch(
                json.loads(event.attributes["junjo.state_json_patch"])
            ).apply(projection, in_place=False)
        assert projection == json.loads(attributes[f"junjo.{namespace}.state.end"])
        evidence.append(
            (
                owner_kind,
                [event.attributes["junjo.store.action"] for event in events],
                attributes["junjo.store.revision.end"],
                attributes["junjo.store.transition.count"],
            )
        )
    return sorted(evidence)


def _store_evidence_from_canonical(
    fixture: dict[str, Any],
) -> list[tuple[str, list[str], int, int]]:
    evidence = []
    for owner in fixture["spans"]:
        attributes = owner["attributes_json"]
        owner_kind = attributes.get("junjo.span_type")
        if owner_kind not in {"agent", "workflow", "subflow"} or (
            owner_kind == "agent"
            and not attributes.get("junjo.agent.state.available")
        ):
            continue
        namespace = "agent" if owner_kind == "agent" else "workflow"
        store_id = attributes[f"junjo.{namespace}.store.id"]
        events = sorted(
            (
                event
                for span in fixture["spans"]
                for event in span["events_json"]
                if event["name"] == "set_state"
                and event["attributes"].get("junjo.store.id") == store_id
            ),
            key=lambda event: event["attributes"]["junjo.store.transition.sequence"],
        )
        projection = json.loads(attributes[f"junjo.{namespace}.state.start"])
        for event in events:
            projection = jsonpatch.JsonPatch(
                json.loads(event["attributes"]["junjo.state_json_patch"])
            ).apply(projection, in_place=False)
        assert projection == json.loads(attributes[f"junjo.{namespace}.state.end"])
        evidence.append(
            (
                owner_kind,
                [event["attributes"]["junjo.store.action"] for event in events],
                attributes["junjo.store.revision.end"],
                attributes["junjo.store.transition.count"],
            )
        )
    return sorted(evidence)


def _assert_actual_parent_identities(spans: tuple[ReadableSpan, ...]) -> None:
    by_id = {span.context.span_id: span for span in spans if span.context is not None}
    for span in spans:
        attributes = span.attributes or {}
        if "junjo.parent_executable_definition_id" not in attributes:
            continue
        candidate = by_id.get(span.parent.span_id) if span.parent is not None else None
        expected_type = attributes.get("junjo.parent_executable_type")
        while candidate is not None:
            candidate_attributes = candidate.attributes or {}
            candidate_type = candidate_attributes.get("junjo.span_type")
            if "junjo.executable_definition_id" in candidate_attributes and (
                expected_type is None or candidate_type == expected_type
            ):
                break
            candidate = (
                by_id.get(candidate.parent.span_id)
                if candidate.parent is not None
                else None
            )
        assert candidate is not None
        candidate_attributes = candidate.attributes or {}
        assert attributes["junjo.parent_executable_definition_id"] == candidate_attributes[
            "junjo.executable_definition_id"
        ]
        assert attributes["junjo.parent_executable_runtime_id"] == candidate_attributes[
            "junjo.executable_runtime_id"
        ]
        assert attributes["junjo.parent_executable_structural_id"] == candidate_attributes[
            "junjo.executable_structural_id"
        ]


def _assert_canonical_parent_identities(fixture: dict[str, Any]) -> None:
    by_id = {span["span_id"]: span for span in fixture["spans"]}
    for span in fixture["spans"]:
        attributes = span["attributes_json"]
        if "junjo.parent_executable_definition_id" not in attributes:
            continue
        candidate = by_id.get(span["parent_span_id"])
        expected_type = attributes.get("junjo.parent_executable_type")
        while candidate is not None:
            candidate_attributes = candidate["attributes_json"]
            candidate_type = candidate_attributes.get("junjo.span_type")
            if "junjo.executable_definition_id" in candidate_attributes and (
                expected_type is None or candidate_type == expected_type
            ):
                break
            candidate = by_id.get(candidate["parent_span_id"])
        assert candidate is not None
        candidate_attributes = candidate["attributes_json"]
        assert attributes["junjo.parent_executable_definition_id"] == candidate_attributes[
            "junjo.executable_definition_id"
        ]
        assert attributes["junjo.parent_executable_runtime_id"] == candidate_attributes[
            "junjo.executable_runtime_id"
        ]
        assert attributes["junjo.parent_executable_structural_id"] == candidate_attributes[
            "junjo.executable_structural_id"
        ]


def test_canonical_agent_producer_fixture_discovery_is_exact() -> None:
    discovered = {path.stem for path in PRODUCER_ROOT.glob("*.json")}
    assert discovered == EXPECTED_SCENARIOS


@pytest.mark.parametrize("scenario", sorted(EXPECTED_SCENARIOS))
@pytest.mark.asyncio
async def test_actual_sdk_export_is_canonical_producer_equivalent(
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
    span_exporter: InMemorySpanExporter,
) -> None:
    fixture = _canonical(scenario)
    assert fixture["scenario"] == scenario
    await _execute_scenario(scenario, monkeypatch)
    spans = span_exporter.get_finished_spans()

    assert _actual_records(spans) == _canonical_records(fixture)
    _assert_actual_parent_identities(spans)
    _assert_canonical_parent_identities(fixture)
    assert _store_evidence_from_actual(spans) == _store_evidence_from_canonical(
        fixture
    )
