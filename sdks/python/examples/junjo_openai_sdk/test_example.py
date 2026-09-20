"""Real OpenAI SDK + OpenInference with deterministic HTTP responses; no paid calls."""

import json
from types import SimpleNamespace

import httpx2 as httpx
import jsonpatch
import pytest
import telemetry
from application import OrderSupportState, OrderSupportStore, SupportRequest, build_agent
from driver import OpenAIModelDriver
from openai import AsyncOpenAI
from openinference.instrumentation.openai import OpenAIInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from junjo import ModelDriverBinding, ModelDriverDescriptor


def decode_payload(value: object):
    assert isinstance(value, str)
    return json.loads(value)


@pytest.mark.parametrize("borrowed", [False, True], ids=["factory-created", "caller-supplied"])
@pytest.mark.parametrize(
    "order_id,eligible,days,branch",
    [("ORD-1001", True, 10, "EligibleReturnNode"), ("ORD-1002", False, 50, "IneligibleReturnNode")],
    ids=["eligible", "ineligible"],
)
async def test_provider_calls_tools_and_shared_state_are_observed(
    monkeypatch, borrowed, order_id, eligible, days, branch
):
    exporter = InMemorySpanExporter()
    monkeypatch.setenv("JUNJO_OTLP_ENDPOINT", "localhost:26155")
    monkeypatch.setenv("JUNJO_AI_STUDIO_API_KEY", "test-only")
    monkeypatch.setattr(
        telemetry, "JunjoOtelExporter", lambda **kwargs: SimpleNamespace(span_processor=SimpleSpanProcessor(exporter))
    )
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", None)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", False)
    provider = telemetry.init_telemetry()
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests)
        if index < 3:
            output = [
                {"type": "reasoning", "id": f"rs_{index}", "summary": [], "encrypted_content": "opaque-continuation"},
                {
                    "type": "function_call",
                    "id": f"fc_{index}",
                    "call_id": f"call_{index}",
                    "name": "lookup_order" if index == 1 else "check_return_eligibility",
                    "arguments": json.dumps({"order_id": order_id} if index == 1 else {}),
                    "status": "completed",
                },
            ]
        else:
            output = [
                {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {"order_id": order_id, "eligible": eligible, "explanation": "Sample answer."}
                            ),
                            "annotations": [],
                        }
                    ],
                }
            ]
        return httpx.Response(
            200,
            json={
                "id": f"resp_{index}",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": body["model"],
                "output": output,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            async with AsyncOpenAI(api_key="test-only", http_client=http) as client:
                model = ModelDriverBinding.per_run(
                    descriptor=ModelDriverDescriptor(
                        driver_key="example-test", provider="openai", model="fixture-model"
                    ),
                    factory=lambda: OpenAIModelDriver(client, "fixture-model"),
                )
                definition = build_agent(model)
                store = OrderSupportStore(OrderSupportState()) if borrowed else None
                result = await definition.execute(
                    SupportRequest(order_id=order_id, question="Can I return this order?"),
                    dependencies=None,
                    store=store,
                )
        spans = exporter.get_finished_spans()
        attributes = [span.attributes for span in spans if span.attributes is not None]
        model_span_ids = {
            span.context.span_id
            for span in spans
            if span.context is not None and (span.attributes or {}).get("junjo.agent.operation_type") == "model_request"
        }
        assert len({span.context.trace_id for span in spans if span.context is not None}) == 1
        for span in spans:
            if (span.attributes or {}).get("openinference.span.kind") == "LLM":
                assert span.parent is not None and span.parent.span_id in model_span_ids
        owner = next(item for item in attributes if item.get("junjo.span_type") == "agent")
        workflow = next(item for item in attributes if item.get("junjo.span_type") == "workflow")
        assert owner["junjo.agent.application_store.id"] == workflow["junjo.workflow.store.id"]
        assert owner["junjo.agent.store.id"] != workflow["junjo.workflow.store.id"]
        assert len([item for item in attributes if item.get("openinference.span.kind") == "LLM"]) == 3
        # Only the eligibility Tool needs a Workflow; lookup executes its Node directly.
        assert len([item for item in attributes if item.get("junjo.span_type") == "workflow"]) == 1
        nodes = [span for span in spans if (span.attributes or {}).get("junjo.span_type") == "node"]
        assert [span.name for span in nodes] == ["LookupOrderNode", "EvaluateReturnPolicyNode", branch]
        lookup_node = nodes[0]
        assert lookup_node.parent is not None
        lookup_operation = next(span for span in spans if span.context.span_id == lookup_node.parent.span_id)
        assert lookup_operation.attributes is not None
        assert lookup_operation.attributes["junjo.agent.operation_type"] == "tool"

        assert result.application_state is not None
        assert result.application_state.order is not None
        assert result.application_state.decision_reason is not None
        assert result.application_state.order.order_id == order_id
        assert result.application_state.days_since_delivery == days
        assert result.application_state.within_return_window is eligible
        assert result.application_state.eligible is eligible
        assert str(days) in result.application_state.decision_reason
        assert result.output.order_id == order_id
        assert result.output.eligible is eligible
        assert result.output.explanation == "Sample answer."
        if store is not None:
            assert result.application_store_id == store.id
            assert await store.get_state() == result.application_state

        # Replay the real application patches with their original writer attribution.
        events = [
            (span, event.attributes or {}) for span in nodes for event in span.events if event.name == "set_state"
        ]
        assert [event["junjo.store.id"] for _, event in events] == [result.application_store_id] * 3
        assert [event["junjo.store.action"] for _, event in events] == [
            "record_order",
            "record_policy_evaluation",
            "record_decision",
        ]
        assert [event["junjo.store.transition.sequence"] for _, event in events] == [1, 2, 3]
        assert (
            owner["junjo.agent.application_store.transition.start"],
            owner["junjo.agent.application_store.transition.end"],
        ) == (0, 3)
        assert (workflow["junjo.store.transition.start"], workflow["junjo.store.transition.end"]) == (1, 3)
        replay = decode_payload(owner["junjo.agent.application_state.start"])
        for index, (_, event) in enumerate(events):
            replay = jsonpatch.apply_patch(replay, decode_payload(event["junjo.state_json_patch"]))
            if index == 0:
                assert replay == decode_payload(workflow["junjo.workflow.state.start"])
                assert replay["order"]["order_id"] == order_id
                assert replay["eligible"] is None
            elif index == 1:
                assert replay["within_return_window"] is eligible
                assert replay["eligible"] is None  # the branch has not recorded its decision yet
        assert replay == decode_payload(owner["junjo.agent.application_state.end"])
        assert replay == decode_payload(workflow["junjo.workflow.state.end"])
        assert replay == result.application_state.model_dump(mode="json")
        assert "explanation" not in replay  # final model output is not automatically written to the Store

        # State reaches the model only through the explicitly projected Tool results.
        assert json.loads(requests[0]["input"][0]["content"]) == {
            "order_id": order_id,
            "question": "Can I return this order?",
        }
        assert requests[1]["input"][-1]["type"] == "function_call_output"
        assert requests[1]["input"][-1]["call_id"] == "call_1"
        lookup_result = json.loads(requests[1]["input"][-1]["output"])
        assert lookup_result == {
            "order": result.application_state.order.model_dump(mode="json"),
            "as_of": "2026-09-20",
            "return_window_days": 30,
        }
        assert any(item.get("encrypted_content") == "opaque-continuation" for item in requests[1]["input"])
        assert requests[2]["input"][-1]["call_id"] == "call_2"
        assert json.loads(requests[2]["input"][-1]["output"]) == {
            "order_id": order_id,
            "eligible": eligible,
            "decision_reason": result.application_state.decision_reason,
        }
        assert len(requests) == 3
        assert result.usage.fields["inputTokens"].sum == 30
    finally:
        OpenAIInstrumentor().uninstrument()
        provider.shutdown()
