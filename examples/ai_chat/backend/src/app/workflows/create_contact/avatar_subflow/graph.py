from junjo.edge import Edge
from junjo.graph import Graph

from app.workflows.create_contact.avatar_subflow.nodes.avatar_inspiration.node import AvatarInspirationNode
from app.workflows.create_contact.avatar_subflow.nodes.create_avatar.node import CreateAvatarNode


def create_avatar_subflow_graph() -> Graph:
    # Instantiate the nodes
    avatar_inspiration = AvatarInspirationNode()
    create_avatar = CreateAvatarNode()

    # Construct the graph for the SubFlow
    return Graph(
        source=avatar_inspiration,
        sink=create_avatar,
        edges=[
            Edge(tail=avatar_inspiration, head=create_avatar)
        ]
    )
