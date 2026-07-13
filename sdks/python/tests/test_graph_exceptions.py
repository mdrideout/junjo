import builtins

import pytest

from junjo import (
    BaseState,
    BaseStore,
    Edge,
    Graph,
    GraphRenderError,
    GraphValidationError,
    Node,
    Workflow,
)


class ExceptionState(BaseState):
    pass


class ExceptionStore(BaseStore[ExceptionState]):
    pass


class StartNode(Node[ExceptionStore]):
    async def service(self, store: ExceptionStore) -> None:
        return


class EndNode(Node[ExceptionStore]):
    async def service(self, store: ExceptionStore) -> None:
        return


@pytest.fixture(autouse=True)
def suppress_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)


def test_graph_requires_non_empty_sinks_with_typed_validation_error() -> None:
    start = StartNode()

    with pytest.raises(GraphValidationError, match="at least one sink"):
        Graph(source=start, sinks=[], edges=[])


@pytest.mark.asyncio
async def test_workflow_dead_end_raises_typed_graph_validation_error() -> None:
    start = StartNode()
    declared_sink = EndNode()
    workflow = Workflow[ExceptionState, ExceptionStore](
        graph_factory=lambda: Graph(
            source=start,
            sinks=[declared_sink],
            edges=[],
        ),
        store_factory=lambda: ExceptionStore(initial_state=ExceptionState()),
    )

    with pytest.raises(GraphValidationError, match="dead-ends without an outgoing edge"):
        await workflow.execute()


def test_export_graphviz_assets_wraps_render_command_failures(
    tmp_path,
) -> None:
    start = StartNode()
    end = EndNode()
    graph = Graph(source=start, sinks=[end], edges=[Edge(tail=start, head=end)])

    with pytest.raises(GraphRenderError, match="Failed to render Graphviz asset"):
        graph.export_graphviz_assets(
            out_dir=tmp_path / "graphviz",
            dot_cmd="definitely-not-a-real-dot-binary",
        )
