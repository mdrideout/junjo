"""Fresh shared image-response Graph construction."""

from junjo import Edge, Graph

from ai_chat.domain.ports import ImageModel, LanguageModel

from .nodes import CreateImageInspirationNode, CreateImageResponseNode


def create_image_graph(*, language: LanguageModel, images: ImageModel) -> Graph:
    inspire = CreateImageInspirationNode(language)
    create = CreateImageResponseNode(language=language, images=images)
    return Graph(source=inspire, sinks=[create], edges=[Edge(tail=inspire, head=create)])
