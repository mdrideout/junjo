"""Create-contact Graph preserving concurrency and avatar Subflow boundaries."""

from junjo import Edge, Graph, RunConcurrent

from ai_chat.domain.ports import ContactWriter, ImageModel, LanguageModel

from .avatar_state import AvatarWorkflowState, AvatarWorkflowStore
from .avatar_subflow import AvatarSubflow, create_avatar_graph
from .nodes import (
    CreateBioNode,
    CreateNameNode,
    CreatePersonalityNode,
    PersistContactNode,
    SelectAgeNode,
    SelectLocationNode,
)


def create_contact_graph(
    *,
    contacts: ContactWriter,
    language: LanguageModel,
    images: ImageModel,
) -> Graph:
    initial_data = RunConcurrent(
        name="Create Initial Contact Data",
        items=[SelectAgeNode(), SelectLocationNode(language), CreatePersonalityNode()],
    )
    bio = CreateBioNode(language)
    name = CreateNameNode(language)
    avatar = AvatarSubflow(
        name="Create Contact Avatar Subflow",
        graph_factory=lambda: create_avatar_graph(language=language, images=images),
        store_factory=lambda: AvatarWorkflowStore(initial_state=AvatarWorkflowState()),
        max_iterations=1,
    )
    persist = PersistContactNode(contacts)
    return Graph(
        source=initial_data,
        sinks=[persist],
        edges=[
            Edge(tail=initial_data, head=bio),
            Edge(tail=bio, head=name),
            Edge(tail=name, head=avatar),
            Edge(tail=avatar, head=persist),
        ],
    )
