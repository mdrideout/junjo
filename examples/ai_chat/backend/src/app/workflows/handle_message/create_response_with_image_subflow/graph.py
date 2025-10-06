from junjo.edge import Edge
from junjo.graph import Graph

from app.workflows.handle_message.create_response_with_image_subflow.nodes.create_image.node import (
    CreateImageNode,
)
from app.workflows.handle_message.create_response_with_image_subflow.nodes.create_image_response.node import (
    CreateImageResponseNode,
)
from app.workflows.handle_message.create_response_with_image_subflow.nodes.image_inspiration.node import (
    ImageInspirationNode,
)


def create_response_with_image_subflow_graph() -> Graph:
    # Instantiate the nodes
    image_inspiration = ImageInspirationNode()
    create_image = CreateImageNode()
    create_image_response = CreateImageResponseNode()

    # Construct the graph for the SubFlow
    return Graph(
        source=image_inspiration,
        sink=create_image_response,
        edges=[
            Edge(tail=image_inspiration, head=create_image),
            Edge(tail=create_image, head=create_image_response),
        ],
    )
