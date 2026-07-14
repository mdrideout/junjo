"""Create-contact Graph preserving concurrency and avatar Subflow boundaries."""

from junjo import Edge, Graph, RunConcurrent

from ai_chat.domain.ports import ContactWriter, ImageRenderer

from .avatar_state import AvatarWorkflowState, AvatarWorkflowStore
from .avatar_subflow import AvatarSubflow, create_avatar_graph
from .nodes import (
    CreateIdentityNode,
    PersistContactNode,
    SelectAgeNode,
    SelectLocationNode,
    SelectPersonalityNode,
)


def create_contact_graph(*, contacts: ContactWriter, images: ImageRenderer) -> Graph:
    initial_data = RunConcurrent(
        name="Create Initial Contact Data",
        items=[SelectAgeNode(), SelectLocationNode(), SelectPersonalityNode()],
    )
    identity = CreateIdentityNode()
    avatar = AvatarSubflow(
        name="Create Contact Avatar Subflow",
        graph_factory=lambda: create_avatar_graph(images),
        store_factory=lambda: AvatarWorkflowStore(initial_state=AvatarWorkflowState()),
        max_iterations=1,
    )
    persist = PersistContactNode(contacts)
    return Graph(
        source=initial_data,
        sinks=[persist],
        edges=[
            Edge(tail=initial_data, head=identity),
            Edge(tail=identity, head=avatar),
            Edge(tail=avatar, head=persist),
        ],
    )
