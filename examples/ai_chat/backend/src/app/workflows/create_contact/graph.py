from junjo.edge import Edge
from junjo.graph import Graph
from junjo.run_concurrent import RunConcurrent

from app.workflows.create_contact.nodes.create_avatar.node import CreateAvatarNode
from app.workflows.create_contact.nodes.create_personality.node import CreatePersonalityNode
from app.workflows.create_contact.nodes.select_location.node import SelectLocationNode
from app.workflows.create_contact.nodes.select_sex.node import SelectSexNode
from app.workflows.create_contact.nodes.sink.node import CreateContactSinkNode

# Nodes
sink_node = CreateContactSinkNode()
select_sex_node = SelectSexNode()
select_location_node = SelectLocationNode()
create_personality_node = CreatePersonalityNode()
create_avatar_node = CreateAvatarNode()

# Concurrently run initial data nodes
initial_data_node = RunConcurrent(
    name="Initial Data",
    items=[
        select_sex_node,
        select_location_node,
        create_personality_node
    ]
)

# Graph
create_contact_graph = Graph(
    source=initial_data_node,
    sink=sink_node,
    edges=[
        # Initial data nodes
        Edge(tail=initial_data_node, head=create_avatar_node),
        Edge(tail=create_avatar_node, head=sink_node),
    ]
)


