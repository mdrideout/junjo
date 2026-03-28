import asyncio
import builtins

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode

from junjo import BaseState, BaseStore, Graph, Node, RunConcurrent, Workflow


class TelemetryState(BaseState):
    pass


class TelemetryStore(BaseStore[TelemetryState]):
    pass


@pytest.fixture(autouse=True)
def suppress_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)

    return exporter


@pytest.mark.asyncio
async def test_run_concurrent_marks_cancelled_sibling_spans(
    span_exporter: InMemorySpanExporter,
) -> None:
    sibling_started = asyncio.Event()
    sibling_cancelled = asyncio.Event()

    class WaitingSiblingNode(Node[TelemetryStore]):
        async def service(self, store: TelemetryStore) -> None:
            sibling_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                sibling_cancelled.set()
                raise

    class FailingNode(Node[TelemetryStore]):
        async def service(self, store: TelemetryStore) -> None:
            await sibling_started.wait()
            raise RuntimeError("boom")

    def create_run_concurrent_graph() -> Graph:
        run_concurrent = RunConcurrent(
            name="Concurrent Execution",
            items=[WaitingSiblingNode(), FailingNode()],
        )
        return Graph(source=run_concurrent, sinks=[run_concurrent], edges=[])

    workflow = Workflow[TelemetryState, TelemetryStore](
        name="Telemetry Workflow",
        graph_factory=create_run_concurrent_graph,
        store_factory=lambda: TelemetryStore(initial_state=TelemetryState()),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await workflow.execute()

    await asyncio.wait_for(sibling_cancelled.wait(), timeout=0.2)

    spans = {span.name: span for span in span_exporter.get_finished_spans()}

    failing_span = spans["FailingNode"]
    sibling_span = spans["WaitingSiblingNode"]

    assert failing_span.status.status_code is StatusCode.ERROR
    assert any(event.name == "exception" for event in failing_span.events)

    assert sibling_span.attributes["junjo.cancelled"] is True
    assert sibling_span.attributes["junjo.cancelled_reason"] == "sibling_failed"
