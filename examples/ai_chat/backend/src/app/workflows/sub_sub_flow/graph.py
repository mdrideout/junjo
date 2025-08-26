from junjo.edge import Edge
from junjo.graph import Graph

from app.workflows.sub_sub_flow.sub_flow_node_1.node import SubSubFlowNode1
from app.workflows.sub_sub_flow.sub_flow_node_2.node import SubSubFlowNode2
from app.workflows.sub_sub_flow.sub_flow_node_3.node import SubSubFlowNode3


def create_sub_sub_flow_graph() -> Graph:
    # Instantiate the nodes
    sub_flow_node_1 = SubSubFlowNode1()
    sub_flow_node_2 = SubSubFlowNode2()
    sub_flow_node_3 = SubSubFlowNode3()

    # Construct the graph for the SubFlow
    return Graph(
        source=sub_flow_node_1,
        sink=sub_flow_node_3,
        edges=[
            Edge(tail=sub_flow_node_1, head=sub_flow_node_2),
            Edge(tail=sub_flow_node_2, head=sub_flow_node_3)
        ]
    )
