from junjo.edge import Edge
from junjo.graph import Graph
from junjo.run_concurrent import RunConcurrent

from app.workflows.create_contact.avatar_subflow.graph import avatar_subflow_graph
from app.workflows.create_contact.avatar_subflow.store import AvatarSubflowState, AvatarSubflowStore
from app.workflows.create_contact.avatar_subflow.sub_flow import AvatarSubFlow
from app.workflows.create_contact.nodes.create_personality.node import CreatePersonalityNode
from app.workflows.create_contact.nodes.select_location.node import SelectLocationNode
from app.workflows.create_contact.nodes.select_sex.node import SelectSexNode
from app.workflows.create_contact.nodes.sink.node import CreateContactSinkNode

# Nodes
sink_node = CreateContactSinkNode()
select_sex_node = SelectSexNode()
select_location_node = SelectLocationNode()
create_personality_node = CreatePersonalityNode()

# Subflows
avatar_subflow = AvatarSubFlow(
    graph=avatar_subflow_graph,
    store=AvatarSubflowStore(
        initial_state=AvatarSubflowState()
    )
)

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
        Edge(tail=initial_data_node, head=avatar_subflow),
        Edge(tail=avatar_subflow, head=sink_node),
    ]
)


