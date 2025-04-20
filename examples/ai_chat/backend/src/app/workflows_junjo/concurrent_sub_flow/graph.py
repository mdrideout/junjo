from junjo.edge import Edge
from junjo.graph import Graph

from app.workflows_junjo.concurrent_sub_flow.sub_flow_node_1.node import ConcurrentSubFlowNode1
from app.workflows_junjo.concurrent_sub_flow.sub_flow_node_2.node import ConcurrentSubFlowNode2
from app.workflows_junjo.concurrent_sub_flow.sub_flow_node_3.node import ConcurrentSubFlowNode3

# Instantiate the nodes
sub_flow_node_1 = ConcurrentSubFlowNode1()
sub_flow_node_2 = ConcurrentSubFlowNode2()
sub_flow_node_3 = ConcurrentSubFlowNode3()

# Construct the graph for the SubFlow
concurrent_sub_flow_graph = Graph(
    source=sub_flow_node_1,
    sink=sub_flow_node_3,
    edges=[
        Edge(tail=sub_flow_node_1, head=sub_flow_node_2),
        Edge(tail=sub_flow_node_2, head=sub_flow_node_3)
    ]
)
