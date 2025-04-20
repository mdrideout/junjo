from junjo.edge import Edge
from junjo.graph import Graph

from app.workflows_junjo.sub_sub_flow.graph import sub_sub_flow_graph
from app.workflows_junjo.sub_sub_flow.state import SubSubFlowState
from app.workflows_junjo.sub_sub_flow.store import SubSubFlowStore
from app.workflows_junjo.sub_sub_flow.sub_flow import SubSubFlow
from app.workflows_junjo.test_sub_flow.sub_flow_node_1.node import SubFlowNode1
from app.workflows_junjo.test_sub_flow.sub_flow_node_2.node import SubFlowNode2
from app.workflows_junjo.test_sub_flow.sub_flow_node_3.node import SubFlowNode3

# Instantiate the nodes
sub_flow_node_1 = SubFlowNode1()
sub_flow_node_2 = SubFlowNode2()
sub_flow_node_3 = SubFlowNode3()

# SubFlow Test - Test Running A SubFlow in a SubFlow graph
sub_sub_flow = SubSubFlow(
    graph=sub_sub_flow_graph,
    store=SubSubFlowStore(initial_state=SubSubFlowState())
)

# Construct the graph for the SubFlow
test_sub_flow_graph = Graph(
    source=sub_flow_node_1,
    sink=sub_flow_node_3,
    edges=[
        Edge(tail=sub_flow_node_1, head=sub_sub_flow),
        Edge(tail=sub_sub_flow, head=sub_flow_node_2),
        Edge(tail=sub_flow_node_2, head=sub_flow_node_3)
    ]
)
