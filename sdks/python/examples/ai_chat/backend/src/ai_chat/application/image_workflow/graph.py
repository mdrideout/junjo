"""Fresh image Workflow Graph construction."""

from junjo import Edge, Graph

from ai_chat.domain.ports import ImageRenderer

from .nodes import PrepareImagePromptNode, RenderImageNode


def create_image_graph(renderer: ImageRenderer) -> Graph:
    prepare = PrepareImagePromptNode()
    render = RenderImageNode(renderer)
    return Graph(
        source=prepare,
        sinks=[render],
        edges=[Edge(tail=prepare, head=render)],
    )
