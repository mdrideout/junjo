import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from junjo import BaseState, BaseStore, ExecutionCorrelation, Node, evaluate_node


class EvalState(BaseState):
    value: str
    result: str | None = None


class EvalStore(BaseStore[EvalState]):
    async def set_result(self, result: str) -> None:
        await self.set_state({"result": result})


class ExampleNode(Node[EvalStore]):
    async def service(self, store: EvalStore) -> None:
        state = await store.get_state()
        await store.set_result(state.value.upper())


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)
    return exporter


@pytest.mark.asyncio
async def test_evaluate_node_uses_normal_workflow_node_and_store_evidence(
    span_exporter: InMemorySpanExporter,
) -> None:
    node = ExampleNode()
    store = EvalStore(initial_state=EvalState(value="one case"))

    result = await evaluate_node(
        node=node,
        store=store,
        correlation=ExecutionCorrelation(type="ai_chat.eval_case", id="bio-001"),
    )

    assert result.node_definition_id == node.id
    assert result.state == EvalState(value="one case", result="ONE CASE")
    current_state = await store.get_state()
    assert result.state is not current_state
    spans = span_exporter.get_finished_spans()
    assert [span.name for span in spans] == ["ExampleNode", "Evaluate ExampleNode"]
    for span in spans:
        assert span.attributes is not None
        assert span.attributes["junjo.correlation.type"] == "ai_chat.eval_case"
        assert span.attributes["junjo.correlation.id"] == "bio-001"
